"""Auth ORM models: Role (dynamic) + User + ApiKey (single-tenant).

RBAC is fully dynamic: roles are rows created by admins, each carrying a chosen
set of permission keys (from permissions.PERMISSIONS). No hardcoded role names.

Uuid/JSON/Enum use SQLAlchemy's portable generic types so the same models run on
Postgres and on SQLite (tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, func, text  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db.base import Base
from .permissions import WILDCARD


class Role(Base):
    """A named bundle of permission keys. Admin-defined (except the system role)."""

    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # list[str] of permission keys, e.g. ["user.read", "audit.read"] or ["*"].
    permissions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # System roles (the built-in Administrator) can't be edited or deleted.
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def grants(self, permission: str) -> bool:
        return WILDCARD in self.permissions or permission in self.permissions


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    # True once the user has proven inbox access (completed an emailed set-password
    # / reset link). Admin-created users start unverified until they use their invite.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Storage key for the user's uploaded profile picture (resolved to a URL at
    # response time via the storage backend). None => fall back to initials.
    avatar_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Per-user preferences (theme, locale, notification opt-ins, …). A free-form
    # JSON blob so scenarios can extend it without a migration.
    preferences: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # --- account security (STQC / auth hardening) --------------------------
    # Brute-force lockout: consecutive failed logins, and a lock expiry after the
    # configured threshold is crossed.
    failed_login_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Password lifecycle: when it was last set (for expiry), recent hashes (to
    # block reuse), and a force-change flag.
    password_changed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # --- two-factor auth (TOTP) --------------------------------------------
    # Fernet-encrypted base32 TOTP secret (set at setup, kept while enrolled).
    totp_secret: Mapped[str | None] = mapped_column(String, nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # SHA-256 hashes of one-time recovery codes (consumed as they're used).
    mfa_recovery_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # Eager-loaded with the user so permission checks never need a second query.
    role: Mapped[Role] = relationship(lazy="selectin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiKey(Base):
    """Machine credential (mobile app, integrations). Carries a role like a user.

    Only a SHA-256 hash of the key + its short ``prefix`` are stored; the raw key
    is shown once at creation.
    """

    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, nullable=False)
    prefix: Mapped[str] = mapped_column(String, index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    role: Mapped[Role] = relationship(lazy="selectin")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RefreshToken(Base):
    """One row per issued refresh token (id = the token's jti). Enables revocation:
    logout / password-change mark rows revoked, and refresh checks the row is live."""

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)  # jti
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Session context — captured at login so the user can review + revoke devices.
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip: Mapped[str | None] = mapped_column(String, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PasswordResetToken(Base):
    """Single-use, time-limited token for the forgot-password flow (only its hash
    is stored)."""

    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
