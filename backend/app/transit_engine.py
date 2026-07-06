"""Transit auto-engine (async port of vizor_nvr scenarios/frs/live/transit_engine).

Turns recognition events into entry→exit sessions. A rule's ``config`` carries
``{entry_camera, exit_cameras[], window_minutes}``. When a recognised person is
seen on a rule's entry camera an ``open`` session is started with a deadline;
seeing them on an exit camera before the deadline ``closes`` it; a periodic sweep
marks past-deadline sessions ``overdue`` and emits a ``transit_overdue`` event.

Adapted to the new module's async SQLAlchemy + UUID models: camera ids in the
rule ``config`` / session ``attributes`` are compared and stored as strings.
Every entry point is defensive — it never raises into the caller (record_event /
the sweep endpoint); it logs and continues.
"""

from __future__ import annotations

import datetime as dt
import uuid
from datetime import timedelta

from sqlalchemy import select

from edge.core.logging import get_logger

from .domain.models import Person, TransitRule, TransitSession

log = get_logger("frs.transit")


def _as_uuid(value):
    """Best-effort coerce a stringified camera/person id back to uuid.UUID."""
    if value is None or isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def on_recognition(
    db,
    *,
    person_id,
    person_name: str | None = None,
    camera_id=None,
    camera_name: str | None = None,
    when: dt.datetime,
    snapshot_key: str | None = None,
    bbox: list | None = None,
    confidence: float | None = None,
) -> None:
    """Drive transit state from a recognised-person sighting.

    ``person_name`` is stored on the session so the UI shows the name;
    ``snapshot_key`` is stored as the entry/exit thumbnail. Uses the caller's
    session; commits its own change so the sighting is durable.
    """
    if not person_id or not camera_id:
        return
    cam = str(camera_id)
    try:
        rules = (
            await db.execute(select(TransitRule).where(TransitRule.enabled.is_(True)))
        ).scalars().all()

        # Exit first: close any open session this sighting satisfies.
        for rule in rules:
            exits = [str(x) for x in ((rule.config or {}).get("exit_cameras") or [])]
            if cam not in exits:
                continue
            open_sess = (
                await db.execute(
                    select(TransitSession)
                    .where(
                        TransitSession.rule_id == rule.id,
                        TransitSession.person_id == person_id,
                        TransitSession.status == "open",
                    )
                    .order_by(TransitSession.started_at.desc())
                )
            ).scalars().first()
            if open_sess:
                open_sess.status = "closed"
                open_sess.ended_at = when
                attrs = dict(open_sess.attributes or {})
                attrs["exit_camera"] = cam
                attrs["exit_ts"] = when.isoformat()
                try:
                    attrs["duration_seconds"] = (
                        int((when - open_sess.started_at).total_seconds())
                        if open_sess.started_at else None
                    )
                except TypeError:
                    attrs["duration_seconds"] = None
                if snapshot_key:
                    attrs["exit_snapshot"] = snapshot_key
                open_sess.attributes = attrs
                await db.commit()
                return  # one sighting closes at most one session

        # Entry: open a new session if none currently open for this rule+person.
        for rule in rules:
            if str((rule.config or {}).get("entry_camera")) != cam:
                continue
            window = int((rule.config or {}).get("window_minutes") or 15)
            existing = (
                await db.execute(
                    select(TransitSession).where(
                        TransitSession.rule_id == rule.id,
                        TransitSession.person_id == person_id,
                        TransitSession.status == "open",
                    )
                )
            ).scalars().first()
            if existing:
                continue
            attrs = {
                "entry_camera": cam,
                "entry_ts": when.isoformat(),
                "deadline": (when + timedelta(minutes=window)).isoformat(),
            }
            if person_name:
                attrs["person_name"] = person_name
            if snapshot_key:
                attrs["entry_snapshot"] = snapshot_key
            # Store the entry face box too, so the overdue event can crop the
            # detected face out of the entry frame (parity with normal events).
            if bbox:
                attrs["entry_bbox"] = list(bbox)
            # Carry the entry camera + recognition confidence so the overdue event
            # can show them (otherwise Camera/Confidence render as "—").
            if camera_name:
                attrs["entry_camera_name"] = camera_name
            if confidence is not None:
                attrs["entry_confidence"] = confidence
            db.add(TransitSession(
                rule_id=rule.id, person_id=person_id, status="open",
                started_at=when, attributes=attrs,
            ))
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — never break the recorder
        log.warning("transit on_recognition failed person=%s cam=%s err=%s", person_id, cam, exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def sweep_overdue(db, now: dt.datetime | None = None) -> int:
    """Mark open sessions past their deadline as ``overdue`` + emit a
    ``transit_overdue`` event per flip so the operator actually sees the alert.
    Returns the count flipped."""
    now = now or dt.datetime.now(dt.timezone.utc)
    flipped: list[dict] = []
    try:
        opens = (
            await db.execute(select(TransitSession).where(TransitSession.status == "open"))
        ).scalars().all()
        for sess in opens:
            dl = (sess.attributes or {}).get("deadline")
            if not dl:
                continue
            try:
                deadline = dt.datetime.fromisoformat(str(dl).replace("Z", "+00:00"))
            except (ValueError, TypeError):
                continue
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=dt.timezone.utc)
            if now > deadline:
                sess.status = "overdue"
                attrs = dict(sess.attributes or {})
                # Carry session context onto the event so the operator sees who,
                # which rule, how long open, and where they entered.
                flipped.append({
                    "session_id": str(sess.id),
                    "rule_id": sess.rule_id,
                    "person_id": sess.person_id,
                    "person_name": attrs.get("person_name"),
                    "entry_camera": attrs.get("entry_camera"),
                    "entry_camera_name": attrs.get("entry_camera_name"),
                    "entry_snapshot": attrs.get("entry_snapshot"),
                    "entry_bbox": attrs.get("entry_bbox"),
                    "entry_confidence": attrs.get("entry_confidence"),
                    "entry_ts": attrs.get("entry_ts"),
                    "deadline": dl,
                    "overdue_seconds": int((now - deadline).total_seconds()),
                })
        if flipped:
            await db.commit()
    except Exception as exc:  # noqa: BLE001 — the sweep must never blow up
        log.warning("transit sweep failed err=%s", exc)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return 0

    # Emit events AFTER the commit so a failed insert never blocks the status flip.
    for f in flipped:
        try:
            await _emit_overdue_event(db, f, now)
        except Exception:  # noqa: BLE001 — alerting must never break the sweep
            pass
    return len(flipped)


async def _emit_overdue_event(db, f: dict, now: dt.datetime) -> None:
    """Write a ``transit_overdue`` FRS event for one flipped session so it surfaces
    in the Events list + live feed like any other recognition alert."""
    from .events import record_event

    # Resolve rule name + the person's display name. The session stores the name at
    # entry time; older sessions only have a person_id — fall back to the gallery.
    rule_name = None
    person_name = f.get("person_name")
    try:
        r = await db.get(TransitRule, f["rule_id"])
        rule_name = r.name if r else None
        if not person_name and f.get("person_id"):
            p = await db.get(Person, f["person_id"])
            person_name = p.full_name if p else None
    except Exception:  # noqa: BLE001
        pass

    name = person_name or (
        f"Person {str(f.get('person_id'))[:8]}" if f.get("person_id") else "Unknown")
    await record_event(
        db,
        event_type="transit_overdue",
        person_id=f.get("person_id"),
        person_name=person_name,
        camera_id=_as_uuid(f.get("entry_camera")),
        snapshot_key=f.get("entry_snapshot"),
        bbox=f.get("entry_bbox") or [],
        triggered_at=now,
        attributes={
            # Stash the resolved name in attributes too — the Events UI reads
            # attributes.person_name for the PERSON column (the FRSEvent row has no
            # name field for the overdue path), so without this it shows "Person <id>".
            "person_name": person_name,
            "rule_id": str(f.get("rule_id")) if f.get("rule_id") else None,
            "rule_name": rule_name,
            "session_id": f.get("session_id"),
            "entry_camera": f.get("entry_camera"),
            "entry_ts": f.get("entry_ts"),
            "deadline": f.get("deadline"),
            "overdue_seconds": f.get("overdue_seconds"),
            "title": f"Transit overdue — {name}" + (f" ({rule_name})" if rule_name else ""),
        },
    )
