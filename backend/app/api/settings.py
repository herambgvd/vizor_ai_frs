"""FRS feature settings (public dashboard + ingest API toggles + key rotation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.db.base import get_db

from .. import settings_store
from ..domain.permissions import FrsPerm

router = APIRouter(prefix="/frs/settings", tags=["frs-settings"])


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.SETTINGS_MANAGE)),
) -> dict:
    return settings_store.as_dict(await settings_store.get_settings_row(db))


@router.put("")
async def update_settings(
    body: dict,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.SETTINGS_MANAGE)),
) -> dict:
    row = await settings_store.get_settings_row(db)
    for key in ("public_dashboard_enabled", "public_show_names", "ingest_api_enabled"):
        if key in body:
            setattr(row, key, bool(body[key]))
    await db.commit()
    await db.refresh(row)
    await audit_record(db, actor=actor, action="frs.settings.update", target_type="frs_settings", target_id="singleton")
    return settings_store.as_dict(row)


@router.post("/ingest-key/rotate")
async def rotate_key(
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.SETTINGS_MANAGE)),
) -> dict:
    key = await settings_store.rotate_ingest_key(db)
    await audit_record(db, actor=actor, action="frs.settings.rotate_key", target_type="frs_settings", target_id="singleton")
    return {"ingest_api_key": key}
