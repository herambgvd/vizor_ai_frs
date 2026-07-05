"""DB-backed OVERRIDES for the built-in email templates.

The built-in templates live in ``templates.DEFAULT_TEMPLATES`` (code). Admins want
those "ready templates" to be CUSTOMISABLE at runtime without a redeploy — so this
module stores per-name overrides in one small table (``email_templates``).

The contract is a simple fall-back chain: if a row exists for a template ``name``
its ``subject``/``html`` win; otherwise the code default is used (see
``templates.render_with_overrides``). An override's ``name`` may match a built-in
key (customising a ready template) OR be a brand-new custom name.

Only the persistence lives here; the render/fall-back logic stays in ``templates``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Select, String, Text, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class EmailTemplate(Base):
    """One row per OVERRIDDEN template. Absence of a row = use the code default."""

    __tablename__ = "email_templates"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Matches a DEFAULT_TEMPLATES key (to customise a built-in) or a custom name —
    # unique so there's at most one override per name.
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # Jinja2 strings, same as the built-ins: ``{{ placeholders }}`` / ``{% if %}``.
    subject: Mapped[str] = mapped_column(String, nullable=False)
    html: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- service functions -------------------------------------------------------
async def get_override(db: AsyncSession, name: str) -> EmailTemplate | None:
    """Fetch the override row for ``name`` — or None if the default should apply."""
    result = await db.execute(select(EmailTemplate).where(EmailTemplate.name == name))
    return result.scalar_one_or_none()


async def upsert_override(
    db: AsyncSession, name: str, subject: str, html: str
) -> EmailTemplate:
    """Create or update the override for ``name`` (subject + html), then commit."""
    row = await get_override(db, name)
    if row is None:
        row = EmailTemplate(name=name, subject=subject, html=html)
        db.add(row)
    else:
        row.subject = subject
        row.html = html
    await db.commit()
    await db.refresh(row)
    return row


async def delete_override(db: AsyncSession, name: str) -> bool:
    """Remove the override for ``name`` (revert to the code default).

    Returns True if a row was deleted, False if there was nothing to delete.
    """
    row = await get_override(db, name)
    if row is None:
        return False
    await db.delete(row)
    await db.commit()
    return True


def list_overrides(db: AsyncSession) -> Select:  # noqa: ARG001 — db kept for a uniform call site
    """A Select of every override, newest first — hand it to ``paginate``."""
    return select(EmailTemplate).order_by(EmailTemplate.updated_at.desc())
