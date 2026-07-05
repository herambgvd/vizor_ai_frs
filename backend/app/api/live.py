"""FRS live feed — most-recent recognitions for the monitoring wall.

Matches vizor_nvr's polling model: the Live page polls this every few seconds
for the newest sightings (the recognition worker writes them; see
:mod:`app.stream_supervisor`). Thin projection over ``frs_events`` scoped to a
short recency window so the feed stays snappy. Gated by ``frs.event.read``.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.storage import get_storage
from edge.db.base import get_db

from ..domain.models import FRSEvent
from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs/live", tags=["frs-live"])


@router.get("")
async def live_feed(
    camera_id: uuid.UUID | None = None,
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Newest recognitions (last 10 minutes), optionally scoped to a camera."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
    stmt = select(FRSEvent).where(FRSEvent.triggered_at >= since)
    if camera_id:
        stmt = stmt.where(FRSEvent.camera_id == camera_id)
    rows = (await db.execute(stmt.order_by(FRSEvent.triggered_at.desc()).limit(limit))).scalars().all()
    storage = get_storage()
    items = []
    for e in rows:
        items.append({
            "id": str(e.id),
            "event_type": e.event_type,
            "person_id": str(e.person_id) if e.person_id else None,
            "person_name": e.person_name,
            "camera_id": str(e.camera_id) if e.camera_id else None,
            "camera_name": e.camera_name,
            "confidence": e.confidence,
            "liveness_score": e.liveness_score,
            "snapshot_url": await storage.url(e.snapshot_key) if e.snapshot_key else None,
            "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
        })
    return {"items": items}
