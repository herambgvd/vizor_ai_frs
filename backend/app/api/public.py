"""Public FRS dashboard — UNAUTHENTICATED aggregate-only stats.

Gated by the ``public_dashboard_enabled`` toggle. Never exposes snapshots or raw
images; person names only when ``public_show_names`` is on. Safe to embed on a
lobby screen.
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.core.errors import NotFoundError
from edge.db.base import get_db

from .. import settings_store
from ..domain.models import FRSEvent

router = APIRouter(prefix="/frs/public", tags=["frs-public"])


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
