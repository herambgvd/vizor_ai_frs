"""Shared recognition-event writer (vizor_nvr FRS db/events parity).

The single path for recording a sighting — used by the ingest API and the live
pipeline. Persists an ``FRSEvent`` row (with authorized/auth_reason/group_name
enrichment), stores the face crop under the encrypted frs/ prefix, upserts its
embedding into the Qdrant snapshots collection (forensic search), rolls the
sighting into direction-aware daily attendance, drives the transit engine, and
notifies the in-process event bus so the public realtime dashboard can push it.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from edge.core.logging import get_logger

from .domain.models import Attendance, FRSEvent, Group, Person

log = get_logger("frs.events")


# ── realtime bus (for the public SSE dashboard) ──────────────────────────────
# Each subscriber gets a bounded asyncio queue; a slow/dead client drops events
# rather than back-pressuring the recorder. In-process, non-blocking fan-out.
_subscribers: set[asyncio.Queue] = set()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers.add(q)
    return q


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def publish(payload: dict) -> None:
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # slow client — drop rather than block the recorder


# Attendance is driven by actual face SIGHTINGS only. Synthetic alerts like
# transit_overdue carry a person_id for context but are not a sighting — they must
# not punch the clock.
_SIGHTING_TYPES = {"face_recognized", "face_unknown", "face_detected"}


async def _touch_attendance(
    db, *, person_id, person_name, camera_id, event_type, event_id, ts, snapshot_key, direction,
) -> None:
    """Roll a recognition into the person's daily attendance, direction-aware.

    Entry camera fills check-in (keeps the earliest); exit camera updates check-out
    (keeps the latest); both/unset is the legacy first-seen / last-seen behaviour.
    The first sighting of the day on an exit camera records a check-out with no entry.
    """
    if not person_id or event_type not in _SIGHTING_TYPES:
        return
    day_key = ts.date().isoformat()
    row = (
        await db.execute(
            select(Attendance).where(Attendance.person_id == person_id, Attendance.day_key == day_key)
        )
    ).scalar_one_or_none()
    dir_ = (direction or "").lower()
    if row is not None:
        if dir_ == "entry":
            if row.check_in_at is None or (ts and ts < row.check_in_at):
                row.check_in_at = ts
                row.check_in_snapshot = snapshot_key
        else:
            # exit + both/unset: keep the latest check-out.
            row.check_out_at = ts
            row.check_out_snapshot = snapshot_key
        if person_name:
            row.person_name = person_name
    elif dir_ == "exit":
        db.add(Attendance(
            person_id=person_id, person_name=person_name, camera_id=camera_id, day_key=day_key,
            check_out_at=ts, check_out_snapshot=snapshot_key,
            sighting_type=event_type, event_id=event_id,
        ))
    else:
        db.add(Attendance(
            person_id=person_id, person_name=person_name, camera_id=camera_id, day_key=day_key,
            check_in_at=ts, check_in_snapshot=snapshot_key,
            sighting_type=event_type, event_id=event_id,
        ))


async def record_event(
    db: AsyncSession,
    *,
    event_type: str,
    person_id=None,
    person_name: str | None = None,
    camera_id=None,
    camera_name: str | None = None,
    confidence: float | None = None,
    bbox=None,
    snapshot_bytes: bytes | None = None,
    snapshot_content_type: str | None = None,
    snapshot_key: str | None = None,
    liveness_score: float | None = None,
    age: str | None = None,
    age_range: str | None = None,
    gender: str | None = None,
    gender_confidence: float | None = None,
    attributes: dict | None = None,
    triggered_at: dt.datetime | None = None,
    direction: str | None = None,   # "entry" | "exit" | "both"/None (per-camera)
    embedding=None,                 # precomputed 512-d face vector (live pipeline)
) -> FRSEvent:
    from fastapi.concurrency import run_in_threadpool

    from edge.core.storage import get_storage

    from . import enroll, gallery, transit_engine

    now = dt.datetime.now(dt.timezone.utc)
    when = triggered_at or now
    attributes = dict(attributes or {})

    # ── Authorization / group enrichment (vizor_nvr parity) ──────────────────
    # A recognised person is authorized only within its validity window; unknown /
    # missing / unregistered faces are not authorized. Surfaced in the event
    # attributes so the UI can announce authorized / not-authorized / unregistered.
    authorized: bool | None = None
    auth_reason: str | None = None
    group_name: str | None = None
    if person_id and event_type == "face_recognized":
        p = await db.get(Person, person_id)
        if p is not None:
            if p.group_id:
                g = await db.get(Group, p.group_id)
                group_name = g.name if g else None
            today = when.date()
            if p.validity_start and today < p.validity_start:
                authorized, auth_reason = False, "validity not started"
            elif p.validity_end and today > p.validity_end:
                authorized, auth_reason = False, "validity expired"
            else:
                authorized, auth_reason = True, None
        else:
            authorized, auth_reason = False, "person not found"
    elif event_type in ("face_unknown", "face_detected"):
        authorized, auth_reason = False, "unregistered"
    attributes.update({
        "authorized": authorized, "auth_reason": auth_reason, "group_name": group_name,
    })

    # ── Alert framing (transit_overdue surfaces loudly) ──────────────────────
    _is_overdue = event_type == "transit_overdue"
    _title = attributes.get("title") if _is_overdue else (
        person_name or ("Face detected" if event_type == "face_detected" else "Unknown face"))

    ev = FRSEvent(
        id=uuid.uuid4(),
        event_type=event_type,
        severity="warning" if _is_overdue else "info",
        title=_title or "Transit overdue",
        detection_type="transit" if _is_overdue else "face",
        person_id=person_id,
        person_name=person_name,
        camera_id=camera_id,
        camera_name=camera_name,
        confidence=confidence,
        bbox=bbox or [],
        liveness_score=liveness_score,
        age=age,
        age_range=age_range,
        gender=gender,
        gender_confidence=gender_confidence,
        attributes=attributes,
    )
    if triggered_at is not None:
        ev.triggered_at = triggered_at
    ts_iso = when.isoformat()

    if snapshot_bytes:
        key = f"frs/events/{ev.id.hex}.jpg"
        await get_storage().put(key, snapshot_bytes, snapshot_content_type or "image/jpeg")
        ev.snapshot_key = key
        # Prefer the embedding the pipeline already computed for this face — the
        # snapshot is a TIGHT crop, so re-detecting a face in it (embed_query) often
        # fails and the forensic snapshots index stays empty (breaking Investigate).
        # Fall back to a probe embed only when no vector was supplied (e.g. ingest).
        if embedding is not None:
            vec = embedding
        else:
            vec = await run_in_threadpool(enroll.embed_query, snapshot_bytes)
        if vec is not None:
            payload = {
                "event_id": str(ev.id),
                "person_id": str(person_id) if person_id else None,
                "person_name": person_name,
                "camera_id": str(camera_id) if camera_id else None,
                "camera_name": camera_name,
                "event_type": event_type,
                "snapshot_key": key,
                "liveness_score": liveness_score,
                "age": age,
                "age_range": age_range,
                "gender": gender,
                "gender_confidence": gender_confidence,
                "bbox": bbox or [],   # face box in the full-frame snapshot (client-side crop)
                "frame_timestamp": ts_iso,
            }
            await run_in_threadpool(gallery.upsert_snapshot, str(ev.id), vec, payload)
    elif snapshot_key:
        # Pre-existing snapshot key (e.g. a transit_overdue carrying the entry crop).
        ev.snapshot_key = snapshot_key

    db.add(ev)
    # Direction-aware daily attendance for actual face sightings.
    await _touch_attendance(
        db, person_id=person_id, person_name=person_name, camera_id=camera_id,
        event_type=event_type, event_id=ev.id, ts=when, snapshot_key=ev.snapshot_key,
        direction=direction,
    )
    await db.commit()
    await db.refresh(ev)

    # Drive the transit engine from a recognised-person sighting (after the event is
    # durable; never lets a transit error break the recorder).
    if event_type == "face_recognized" and person_id:
        try:
            await transit_engine.on_recognition(
                db, person_id=person_id, person_name=person_name, camera_id=camera_id,
                camera_name=ev.camera_name, when=when, snapshot_key=ev.snapshot_key,
                bbox=ev.bbox, confidence=ev.confidence,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("transit on_recognition raised: %s", exc)

    # Notify the realtime dashboard (aggregate-safe: name only, no snapshot bytes).
    publish({
        "id": str(ev.id),
        "event_type": event_type,
        "camera_id": str(camera_id) if camera_id else None,
        "camera_name": camera_name,
        "person_id": str(person_id) if person_id else None,
        "person_name": person_name,
        "authorized": authorized,
        "auth_reason": auth_reason,
        "group_name": group_name,
        # Browser-usable path through the decrypting /files proxy (frontend fileUrl
        # resolves this), not the raw storage key.
        "snapshot_url": f"/files/{ev.snapshot_key}" if ev.snapshot_key else None,
        "bbox": ev.bbox,          # [x1,y1,x2,y2] pixels — drives the Live overlay box
        "triggered_at": ts_iso,
    })
    return ev
