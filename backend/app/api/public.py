"""Public FRS dashboard — UNAUTHENTICATED aggregate-only stats.

Gated by the ``public_dashboard_enabled`` toggle. Never exposes snapshots or raw
images; person names only when ``public_show_names`` is on. Safe to embed on a
lobby screen.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.core.errors import NotFoundError
from edge.db.base import get_db, get_sessionmaker

from .. import events as events_bus, settings_store
from ..domain.models import FRSEvent

router = APIRouter(prefix="/frs/public", tags=["frs-public"])

# Keepalive cadence (seconds) — see app.api.live for rationale.
_SSE_KEEPALIVE_S = 15


@router.get("/dashboard")
async def public_dashboard(db: AsyncSession = Depends(get_db)) -> dict:
    row = await settings_store.get_settings_row(db)
    if not row.public_dashboard_enabled:
        raise NotFoundError("public dashboard is disabled")

    now = dt.datetime.now(dt.timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    recent = now - dt.timedelta(minutes=15)

    async def _count(*conds):
        return int(await db.scalar(select(func.count()).select_from(FRSEvent).where(*conds)) or 0)

    return {
        "recognized_today": await _count(FRSEvent.event_type == "face_recognized", FRSEvent.triggered_at >= day_start),
        "unknown_today": await _count(FRSEvent.event_type == "face_unknown", FRSEvent.triggered_at >= day_start),
        "spoof_today": await _count(FRSEvent.event_type == "spoof_detected", FRSEvent.triggered_at >= day_start),
        "present_15m": int(await db.scalar(
            select(func.count(func.distinct(FRSEvent.person_id))).where(
                FRSEvent.event_type == "face_recognized", FRSEvent.triggered_at >= recent
            )
        ) or 0),
        "updated_at": now.isoformat(),
    }


@router.get("/live")
async def public_live(db: AsyncSession = Depends(get_db)) -> dict:
    """Recent recognitions (aggregate; names only if ``public_show_names``)."""
    row = await settings_store.get_settings_row(db)
    if not row.public_dashboard_enabled:
        raise NotFoundError("public dashboard is disabled")
    rows = (
        await db.execute(
            select(FRSEvent).where(FRSEvent.event_type == "face_recognized")
            .order_by(FRSEvent.triggered_at.desc()).limit(20)
        )
    ).scalars().all()
    return {
        "items": [
            {"time": e.triggered_at.isoformat() if e.triggered_at else None,
             "name": (e.person_name if row.public_show_names else "Recognised")}
            for e in rows
        ]
    }


@router.get("/stream")
async def public_stream(request: Request) -> StreamingResponse:
    """UNAUTHENTICATED realtime SSE feed for the public lobby dashboard.

    Same in-process event bus as the authenticated Live wall, but every frame is cut
    down to the public-safe subset: type / camera / authorized / group and — only when
    ``public_show_names`` is on — the person name. Never emits snapshots, person ids,
    or the internal ``auth_reason``. Gated by ``public_dashboard_enabled`` (404 when
    off, so the surface simply doesn't exist). Sends ``: keepalive`` every ~15s and
    unsubscribes on disconnect.
    """
    async with get_sessionmaker()() as db:  # short-lived — settings read at connect
        row = await settings_store.get_settings_row(db)
        enabled = bool(row.public_dashboard_enabled)
        show_names = bool(row.public_show_names)
    if not enabled:
        raise NotFoundError("public dashboard is disabled")

    q = events_bus.subscribe()

    def _safe(item: dict) -> dict:
        # Aggregate-safe projection: no snapshot_url, no person_id, no auth_reason.
        return {
            "id": item.get("id"),
            "event_type": item.get("event_type"),
            "camera_id": item.get("camera_id"),
            "camera_name": item.get("camera_name"),
            "person_name": (item.get("person_name") if show_names else None),
            "authorized": item.get("authorized"),
            "group_name": item.get("group_name"),
            "triggered_at": item.get("triggered_at"),
        }

    async def _gen():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=_SSE_KEEPALIVE_S)
                    yield f"data: {json.dumps(_safe(item))}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events_bus.unsubscribe(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
