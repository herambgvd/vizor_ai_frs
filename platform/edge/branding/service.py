"""BrandingService logic — the single-row white-label config (writes commit).

Branding is a singleton: there is one row for the whole deployment. Every helper
here funnels through ``get_or_create`` so callers never have to worry about whether
the row exists yet. As with the rest of the codebase, the session does NOT
auto-commit — each mutating helper commits explicitly.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Branding
from .schemas import UpdateBrandingIn


async def get_or_create(db: AsyncSession) -> Branding:
    """Return the one branding row, creating it with defaults if none exists.

    The model column defaults (app_name="Vizor", the two colours) apply on insert,
    so a fresh deployment gets sensible branding out of the box.
    """
    result = await db.execute(select(Branding))
    branding = result.scalars().first()
    if branding is None:
        branding = Branding()  # all fields fall back to their column defaults
        db.add(branding)
        await db.commit()
        await db.refresh(branding)
    return branding


async def update(db: AsyncSession, data: UpdateBrandingIn) -> Branding:
    """Apply a partial update to the singleton branding row.

    Only fields the caller actually sent (``exclude_unset``) are written, so an
    omitted field keeps its current value rather than being reset to None.
    """
    branding = await get_or_create(db)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(branding, field, value)
    await db.commit()
    await db.refresh(branding)
    return branding


async def set_logo(db: AsyncSession, logo_key: str) -> Branding:
    """Point the branding row at a newly uploaded logo (a storage key)."""
    branding = await get_or_create(db)
    branding.logo_key = logo_key
    await db.commit()
    await db.refresh(branding)
    return branding
