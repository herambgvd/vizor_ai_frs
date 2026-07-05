"""SettingsService — read the effective system settings, and write overrides.

Effective value = the stored override if present, else the catalog default. Writes
only persist known keys (catalog-validated) and commit explicitly, matching the
rest of the codebase's no-autocommit convention.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import catalog
from .models import AppSetting


class SettingsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def all_values(self) -> dict:
        """Every setting's effective value (defaults merged with stored overrides)."""
        rows = (await self.db.execute(select(AppSetting))).scalars().all()
        values = catalog.defaults()
        for row in rows:
            if row.key in values:  # ignore stale keys no longer in the catalog
                values[row.key] = row.value
        return values

    async def public_values(self) -> dict:
        """Only the settings marked public (safe for unauthenticated clients)."""
        allowed = catalog.public_keys()
        return {k: v for k, v in (await self.all_values()).items() if k in allowed}

    async def get(self, key: str):
        return (await self.all_values()).get(key)

    async def update(self, patch: dict) -> dict:
        """Persist overrides for known keys only. Returns the new effective values."""
        known = catalog.known_keys()
        for key, value in patch.items():
            if key not in known:
                continue
            row = await self.db.get(AppSetting, key)
            if row is None:
                self.db.add(AppSetting(key=key, value=value))
            else:
                row.value = value
        await self.db.commit()
        return await self.all_values()
