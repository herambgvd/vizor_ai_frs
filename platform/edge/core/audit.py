"""Audit log — an append-only record of *who did what, to what, when*.

Security-sensitive and compliance-relevant apps must be able to answer questions
like "who deleted that user?" or "when was the license replaced?". The audit log
is the answer: services call ``record(...)`` at the moment a meaningful action
happens, and admins read the trail through ``GET /api/audit``.

Design notes:
  * It is APPEND-ONLY — there is no update/delete endpoint. Tampering with an
    audit trail defeats its purpose.
  * ``record`` takes the acting ``User`` (or None for system/anonymous actions)
    and reads ``actor.id`` / ``actor.email`` DEFENSIVELY via getattr, so callers
    can pass any user-like object (or None) without crashing.
  * ``meta`` is a free-form JSON blob for action-specific context (old/new values,
    request ip, target name) — portable JSON so it works on Postgres and SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, DateTime, String, Uuid, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..auth.deps import require_permission
from ..auth.permissions import CorePerm
from ..db.base import Base, get_db
from .errors import ValidationError
from .pagination import Page, PageParams, page_params, paginate


class AuditLog(Base):
    """One immutable row per audited action."""

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Actor snapshot: we store BOTH the id and the email at the time of the action.
    # The email is captured verbatim so the trail stays readable even if the user
    # is later renamed or deleted (the FK would otherwise dangle). Nullable for
    # system / anonymous actions.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String, nullable=True)
    # What happened, e.g. "user.delete", "license.replace", "role.update".
    action: Mapped[str] = mapped_column(String, nullable=False)
    # What it happened to (optional): a type name + its id, e.g. ("user", "<uuid>").
    target_type: Mapped[str | None] = mapped_column(String, nullable=True)
    target_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Free-form structured context for this action (old/new values, ip, etc.).
    meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # When it happened. Indexed because the log is almost always queried by time.
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


async def record(
    db: AsyncSession,
    *,
    actor: Any | None = None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    meta: dict | None = None,
) -> AuditLog:
    """Write one audit entry and commit it.

    ``actor`` is an ``edge.auth.models.User`` (or None). We read its id/email via
    getattr so any user-like object — or None — is accepted without raising. The
    entry is committed immediately: an audit record must survive even if the
    surrounding request later fails.
    """
    entry = AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_email=getattr(actor, "email", None),
        action=action,
        target_type=target_type,
        target_id=target_id,
        meta=meta or {},
    )
    db.add(entry)
    # The shared session does NOT auto-commit (see db/base.py), so commit here.
    await db.commit()
    await db.refresh(entry)
    return entry


class AuditLogOut(BaseModel):
    """API representation of one audit entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_id: uuid.UUID | None
    actor_email: str | None
    action: str
    target_type: str | None
    target_id: str | None
    meta: dict
    ts: datetime


audit_router = APIRouter(prefix="/audit", tags=["audit"])


@audit_router.get("", response_model=Page[AuditLogOut])
async def list_audit(
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission(CorePerm.AUDIT_READ)),
) -> Page[AuditLogOut]:
    """List audit entries, newest first. Requires the ``audit.read`` permission."""
    stmt = select(AuditLog).order_by(AuditLog.ts.desc())
    return await paginate(db, stmt, params, item_model=AuditLogOut)


# --- Data retention ----------------------------------------------------------
async def _retention_days(db: AsyncSession) -> int:
    """The configured audit retention in days (0 = keep forever)."""
    from ..settings.service import SettingsService  # lazy: avoids an import cycle

    try:
        return int(await SettingsService(db).get("audit_retention_days") or 0)
    except (TypeError, ValueError):
        return 0


class RetentionOut(BaseModel):
    retention_days: int
    total: int


class PurgeIn(BaseModel):
    """Purge entries older than this many days. Omit to use the configured policy."""

    older_than_days: int | None = None


@audit_router.get("/retention", response_model=RetentionOut)
async def audit_retention(
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_permission(CorePerm.AUDIT_READ)),
) -> RetentionOut:
    """Current retention policy + total number of stored audit entries."""
    total = int(await db.scalar(select(func.count()).select_from(AuditLog)) or 0)
    return RetentionOut(retention_days=await _retention_days(db), total=total)


@audit_router.post("/purge")
async def purge_audit(
    data: PurgeIn,
    db: AsyncSession = Depends(get_db),
    actor=Depends(require_permission(CorePerm.SETTINGS_MANAGE)),
) -> dict:
    """Delete audit entries older than N days now (manual retention enforcement).

    Uses ``older_than_days`` if given, else the configured ``audit_retention_days``.
    Gated by ``settings.manage`` because it destroys records permanently.
    """
    days = data.older_than_days if data.older_than_days is not None else await _retention_days(db)
    if not days or days <= 0:
        raise ValidationError("Set a positive number of days (or a retention policy) to purge.")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(delete(AuditLog).where(AuditLog.ts < cutoff))
    await db.commit()
    deleted = result.rowcount or 0
    # Leave a trail of the purge itself (this entry is newer than the cutoff).
    await record(
        db, actor=actor, action="audit.purge", target_type="audit", target_id="bulk",
        meta={"older_than_days": days, "deleted": deleted},
    )
    return {"deleted": deleted, "older_than_days": days}
