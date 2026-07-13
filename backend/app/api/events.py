"""FRS recognition events log — list / filter / delete + operator feedback.

Ported from vizor_nvr FRS `routers/reports.py` (events + feedback). Reads the
shared ``frs_events`` substrate written by the ingest API and the live pipeline.
Deleting an event also purges its encrypted snapshot + Qdrant embedding.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.core.errors import NotFoundError
from edge.core.logging import get_logger
from edge.core.storage import get_storage
from edge.db.base import get_db

from .. import gallery
from ..domain.models import FRSEvent, FRSFeedback, Person
from ..domain.permissions import FrsPerm
from ._scope import allowed_camera_ids
from .schemas import EventBulkDelete, EventOut, EventPage, FeedbackCreate

log = get_logger("frs.events")

router = APIRouter(prefix="/frs/events", tags=["frs-events"])


def _apply_filters(stmt, *, camera_id, person_id, event_type, since, until):
    if camera_id:
        stmt = stmt.where(FRSEvent.camera_id == camera_id)
    if person_id:
        stmt = stmt.where(FRSEvent.person_id == person_id)
    if event_type:
        stmt = stmt.where(FRSEvent.event_type == event_type)
    if since:
        stmt = stmt.where(FRSEvent.triggered_at >= since)
    if until:
        stmt = stmt.where(FRSEvent.triggered_at <= until)
    return stmt


@router.get("", response_model=EventPage)
async def list_events(
    camera_id: uuid.UUID | None = None,
    person_id: uuid.UUID | None = None,
    event_type: str | None = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    cam_scope: set | None = Depends(allowed_camera_ids),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> EventPage:
    base = _apply_filters(select(FRSEvent), camera_id=camera_id, person_id=person_id, event_type=event_type, since=since, until=until)
    # C12 per-camera visibility scope (None = unrestricted).
    if cam_scope is not None:
        base = base.where(FRSEvent.camera_id.in_(cam_scope))
    total = int(await db.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = (
        await db.execute(base.order_by(FRSEvent.triggered_at.desc()).limit(limit).offset(offset))
    ).scalars().all()

    # Latest feedback verdict per event in this page.
    ids = [e.id for e in rows]
    verdicts: dict[uuid.UUID, bool] = {}
    if ids:
        fb_rows = (
            await db.execute(
                select(FRSFeedback.event_id, FRSFeedback.is_correct, FRSFeedback.created_at)
                .where(FRSFeedback.event_id.in_(ids))
                .order_by(FRSFeedback.created_at.desc())
            )
        ).all()
        for ev_id, is_correct, _ts in fb_rows:
            verdicts.setdefault(ev_id, is_correct)  # first = latest (desc order)

    # Enrolled thumbnails of the matched persons in this page (for the Match column).
    person_ids = {e.person_id for e in rows if e.person_id}
    thumbs: dict[uuid.UUID, str] = {}
    if person_ids:
        prows = (
            await db.execute(select(Person.id, Person.thumbnail_key).where(Person.id.in_(person_ids)))
        ).all()
        thumbs = {pid: tk for pid, tk in prows if tk}

    storage = get_storage()
    items = []
    for e in rows:
        out = EventOut.model_validate(e)
        out.snapshot_url = await storage.url(e.snapshot_key) if e.snapshot_key else None
        tk = thumbs.get(e.person_id)
        out.match_thumb_url = await storage.url(tk) if tk else None
        if e.id in verdicts:
            out.feedback = "correct" if verdicts[e.id] else "wrong"
        items.append(out)
    return EventPage(items=items, total=total, limit=limit, offset=offset)


async def _purge_one(db: AsyncSession, e: FRSEvent) -> None:
    """Delete an event's snapshot (storage + Qdrant) then the row itself."""
    if e.snapshot_key:
        try:
            await get_storage().delete(e.snapshot_key)
        except Exception as exc:  # noqa: BLE001
            log.warning("snapshot delete failed event=%s err=%s", e.id, exc)
    try:
        await run_in_threadpool(gallery.delete_snapshot, str(e.id))
    except Exception as exc:  # noqa: BLE001
        log.warning("qdrant snapshot delete failed event=%s err=%s", e.id, exc)
    await db.delete(e)


@router.delete("/{event_id}", status_code=204)
async def delete_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.EVENT_MANAGE)),
) -> None:
    e = await db.get(FRSEvent, event_id)
    if e is None:
        raise NotFoundError("event not found")
    await _purge_one(db, e)
    await db.commit()
    await audit_record(db, actor=actor, action="frs.event.delete", target_type="frs_event", target_id=str(event_id), meta={})


@router.post("/delete")
async def bulk_delete_events(
    data: EventBulkDelete,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.EVENT_MANAGE)),
) -> dict:
    if data.all_matching:
        stmt = _apply_filters(select(FRSEvent), camera_id=data.camera_id, person_id=None, event_type=data.event_type, since=data.since, until=data.until)
    elif data.ids:
        stmt = select(FRSEvent).where(FRSEvent.id.in_(data.ids))
    else:
        return {"deleted": 0}
    rows = (await db.execute(stmt)).scalars().all()
    for e in rows:
        await _purge_one(db, e)
    await db.commit()
    await audit_record(db, actor=actor, action="frs.event.bulk_delete", target_type="frs_event", target_id="*", meta={"count": len(rows)})
    return {"deleted": len(rows)}


# Feedback lives under its own path so it reads naturally: POST /frs/feedback.
feedback_router = APIRouter(prefix="/frs/feedback", tags=["frs-events"])


@feedback_router.post("", status_code=201)
async def submit_feedback(
    data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.EVENT_MANAGE)),
) -> dict:
    e = await db.get(FRSEvent, data.event_id)
    if e is None:
        raise NotFoundError("event not found")
    # One verdict per event: replace any prior feedback.
    await db.execute(sa_delete(FRSFeedback).where(FRSFeedback.event_id == data.event_id))
    fb = FRSFeedback(
        event_id=data.event_id,
        is_correct=data.is_correct,
        matched_person_id=data.matched_person_id or e.person_id,
        actual_person_id=data.actual_person_id,
        note=data.note,
        operator=getattr(actor, "email", None),
    )
    db.add(fb)
    await db.commit()
    await audit_record(db, actor=actor, action="frs.event.feedback", target_type="frs_event", target_id=str(data.event_id), meta={"is_correct": data.is_correct})
    return {"ok": True, "verdict": "correct" if data.is_correct else "wrong"}
