"""FCM push notifications for the React Native mobile app.

Two pieces:
  * ``DeviceToken`` — the FCM registration tokens a user's devices have registered.
    A user can have several (phone + tablet, reinstalls, ...), so we key on the
    token itself (unique) and index by user for fast lookup at send time.
  * ``send_push`` — pushes a title/body to a list of tokens via FCM's legacy HTTP
    API, authorised with the ``server_key`` from the DB-stored "push" channel config.

Like the other channels, config is dynamic (admin-set, encrypted at rest) and all
network work is wrapped so a delivery failure never breaks the caller.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import httpx
from sqlalchemy import DateTime, String, Uuid, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..core.logging import get_logger
from ..db.base import Base
from .config import get_channel, get_config_decrypted

log = get_logger("edge.messaging.push")

# FCM legacy HTTP endpoint. Auth header is ``Authorization: key=<server_key>``.
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"


class DeviceToken(Base):
    """An FCM registration token for one of a user's mobile devices."""

    __tablename__ = "device_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    token: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    # "android" | "ios" — handy for platform-specific payloads later.
    platform: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


async def register_device(db: AsyncSession, user, token: str, platform: str) -> DeviceToken:
    """Register (or re-point) an FCM token for ``user``. Upsert keyed on the token.

    FCM tokens can migrate between users/reinstalls, so if the token already
    exists we just re-associate it with the current user instead of duplicating.
    """
    result = await db.execute(select(DeviceToken).where(DeviceToken.token == token))
    row = result.scalar_one_or_none()
    if row is None:
        row = DeviceToken(user_id=user.id, token=token, platform=platform)
        db.add(row)
    else:
        row.user_id = user.id
        row.platform = platform
    await db.commit()
    await db.refresh(row)
    return row


async def send_push(
    db: AsyncSession,
    tokens: list[str],
    title: str,
    body: str,
    data: dict | None = None,
) -> bool:
    """Send a push notification to ``tokens`` via FCM.

    Returns True on a successful POST, False if the channel is off / no tokens /
    errored. Expected config field: server_key.
    """
    if not tokens:
        log.info("send_push called with no tokens; skipping")
        return False

    row = await get_channel(db, "push")
    if row is None or not row.enabled:
        log.info("push channel not configured or disabled; skipping send")
        return False
    cfg = await get_config_decrypted(db, "push") or {}
    server_key = cfg.get("server_key")
    if not server_key:
        log.warning("push channel missing server_key; skipping send")
        return False

    payload = {
        "registration_ids": tokens,
        "notification": {"title": title, "body": body},
    }
    if data:
        payload["data"] = data

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                FCM_ENDPOINT,
                headers={"Authorization": f"key={server_key}"},
                json=payload,
            )
        resp.raise_for_status()
        log.info("push sent to %d device(s): %s", len(tokens), title)
        return True
    except Exception:  # never let a push failure break the caller
        log.exception("failed to send push to %d token(s)", len(tokens))
        return False
