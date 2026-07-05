"""Dynamic per-channel notification config, stored in the DB (secrets encrypted).

Each delivery channel (email / push / webhook) is configured from the admin UI —
NOT from .env — because credentials differ per deployment and change at runtime.
So the config lives in one small table (``channel_configs``): one row per channel,
an ``enabled`` flag, and a free-form JSON ``config`` blob whose shape depends on the
channel.

Sensitive fields inside that JSON (the SMTP password, the FCM server key, the
webhook signing secret) MUST NOT sit in the DB as plaintext. We encrypt exactly
those fields on the way in (``upsert_channel``) and decrypt them on the way out
(``get_config_decrypted``). For GET responses shown in the UI we ``masked`` them to
``"***"`` so a secret is never returned over the wire.

Which fields are secret, per channel, is declared once in ``SECRET_FIELDS``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..core.secrets import decrypt_secret, encrypt_secret
from ..db.base import Base

# Which JSON keys hold secrets, per channel. Only these are encrypted at rest and
# masked in GET responses; everything else (host, port, url, ...) is plain config.
SECRET_FIELDS: dict[str, list[str]] = {
    "email": ["password"],
    "push": ["server_key"],
    "webhook": ["secret"],
}


class ChannelConfig(Base):
    """One row per delivery channel. ``config`` is a JSON blob (secrets encrypted)."""

    __tablename__ = "channel_configs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # "email" | "push" | "webhook" — one config per channel, hence unique.
    channel: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-form per-channel settings. Secret fields are stored ENCRYPTED here.
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# --- service functions -------------------------------------------------------
async def get_channel(db: AsyncSession, channel: str) -> ChannelConfig | None:
    """Fetch the raw row for a channel (secrets still encrypted). None if unset."""
    result = await db.execute(select(ChannelConfig).where(ChannelConfig.channel == channel))
    return result.scalar_one_or_none()


async def upsert_channel(
    db: AsyncSession, channel: str, enabled: bool, config: dict
) -> ChannelConfig:
    """Create or update a channel's config, encrypting its secret fields first.

    ``config`` comes from the admin UI with secrets in PLAINTEXT; we encrypt the
    declared ``SECRET_FIELDS`` for that channel before persisting.
    """
    # Copy so we never mutate the caller's dict, and encrypt the secret fields.
    stored = dict(config)
    for field in SECRET_FIELDS.get(channel, []):
        if stored.get(field):  # only encrypt non-empty values
            stored[field] = encrypt_secret(str(stored[field]))

    row = await get_channel(db, channel)
    if row is None:
        row = ChannelConfig(channel=channel, enabled=enabled, config=stored)
        db.add(row)
    else:
        row.enabled = enabled
        row.config = stored
    await db.commit()
    await db.refresh(row)
    return row


async def get_config_decrypted(db: AsyncSession, channel: str) -> dict | None:
    """Return the channel's config with secret fields DECRYPTED — for senders.

    Returns None if the channel has never been configured. (Callers separately
    check ``enabled``.)
    """
    row = await get_channel(db, channel)
    if row is None:
        return None
    decrypted = dict(row.config or {})
    for field in SECRET_FIELDS.get(channel, []):
        if decrypted.get(field):
            decrypted[field] = decrypt_secret(str(decrypted[field]))
    return decrypted


def masked(config: dict, channel: str) -> dict:
    """Return a copy of ``config`` with secret fields replaced by ``"***"``.

    Used for GET responses so a stored secret is never sent back to the client.
    """
    safe = dict(config or {})
    for field in SECRET_FIELDS.get(channel, []):
        if field in safe and safe.get(field):
            safe[field] = "***"
    return safe
