"""FRS feature settings (public dashboard + ingest API toggles + key rotation)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.core.audit import record as audit_record
from edge.db.base import get_db

from .. import settings_store
from ..domain.permissions import FrsPerm
from .schemas import FrsSettingsUpdate

router = APIRouter(prefix="/frs/settings", tags=["frs-settings"])


@router.get("")
async def get_settings(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.SETTINGS_MANAGE)),
) -> dict:
    return settings_store.as_dict(await settings_store.get_settings_row(db))


@router.put("")
async def update_settings(
    body: FrsSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(FrsPerm.SETTINGS_MANAGE)),
) -> dict:
    row = await settings_store.get_settings_row(db)
    # Only the public-dashboard / ingest feature toggles are settable here.
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(row, key, bool(value))
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
