"""In-app notifications — the notification bell in the UI.

Every notification we send also lands here as a ``Notification`` row for the target
user, so the app can show an unread badge and a history even when email/push are
off. This is the one channel that's always on.

Kept deliberately small: create, a paginatable list query (newest first), and a
mark-as-read that's scoped to the owning user so one user can't read another's.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..core.logging import get_logger
from ..db.base import Base

log = get_logger("edge.messaging.inapp")


class Notification(Base):
    """A single in-app notification for one user."""

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    body: Mapped[str | None] = mapped_column(String, nullable=True)
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Indexed because we always order/paginate by it (newest first).
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )


async def create_notification(
    db: AsyncSession, user_id, title: str, body: str | None = None
) -> Notification:
    """Insert an in-app notification for ``user_id`` and commit it."""
    row = Notification(user_id=user_id, title=title, body=body)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


def list_query(user_id):
    """A SELECT of a user's notifications, newest first — pass to ``paginate``."""
    return (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.ts.desc())
    )


async def mark_read(db: AsyncSession, notif_id, user_id) -> Notification | None:
    """Mark one notification read — only if it belongs to ``user_id``.

    Returns the updated row, or None if it doesn't exist / isn't the user's (the
    router turns that None into a 404 so callers can't probe others' ids).
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notif_id, Notification.user_id == user_id
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        return None
    row.read = True
    await db.commit()
    await db.refresh(row)
    return row
