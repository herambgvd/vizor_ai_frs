"""Shared recognition-event writer.

The single path for recording a sighting — used by the ingest API (and, later, the
live pipeline). Persists an ``FRSEvent`` row, stores the face crop under the
encrypted frs/ prefix, and upserts its embedding into the Qdrant snapshots
collection so it's findable by forensic search (Investigate).
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from edge.core.logging import get_logger

from .domain.models import Attendance, FRSEvent

log = get_logger("frs.events")


async def _touch_attendance(db, *, person_id, person_name, camera_id, ts, snapshot_key) -> None:
    """Roll a recognition into the person's daily attendance (first in / last out)."""
    if not person_id:
        return
    day_key = ts.date().isoformat()
    row = (
        await db.execute(
            select(Attendance).where(Attendance.person_id == person_id, Attendance.day_key == day_key)
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(Attendance(
            person_id=person_id, person_name=person_name, camera_id=camera_id, day_key=day_key,
            check_in_at=ts, check_in_snapshot=snapshot_key,
        ))
    else:
        row.check_out_at = ts
        row.check_out_snapshot = snapshot_key
        if person_name:
            row.person_name = person_name


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
    liveness_score: float | None = None,
    age: str | None = None,
    age_range: str | None = None,
    gender: str | None = None,
    gender_confidence: float | None = None,
    attributes: dict | None = None,
    triggered_at: dt.datetime | None = None,
) -> FRSEvent:
    from fastapi.concurrency import run_in_threadpool

    from edge.core.storage import get_storage

    from . import enroll, gallery

    ev = FRSEvent(
        id=uuid.uuid4(),
        event_type=event_type,
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
        attributes=attributes or {},
    )
    if triggered_at is not None:
        ev.triggered_at = triggered_at
    ts = (triggered_at or dt.datetime.now(dt.timezone.utc)).isoformat()

    if snapshot_bytes:
        key = f"frs/events/{ev.id.hex}.jpg"
        await get_storage().put(key, snapshot_bytes, snapshot_content_type or "image/jpeg")
        ev.snapshot_key = key
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
                "frame_timestamp": ts,
            }
            await run_in_threadpool(gallery.upsert_snapshot, str(ev.id), vec, payload)

    db.add(ev)
    # A recognised person also updates their daily attendance.
    if event_type == "face_recognized" and person_id:
        await _touch_attendance(
            db, person_id=person_id, person_name=person_name, camera_id=camera_id,
            ts=(triggered_at or dt.datetime.now(dt.timezone.utc)), snapshot_key=ev.snapshot_key,
        )
    await db.commit()
    await db.refresh(ev)
    return ev
