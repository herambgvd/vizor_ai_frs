"""Branding ORM model — the app's white-label identity (single row).

A deployment can be re-skinned for a client (name, logo, brand colours) without a
code change. There is exactly ONE branding row for the whole app (single-tenant),
so the service treats it as a singleton: read-or-create the one row, then update it.

Portable generic types (Uuid/String/Boolean/DateTime) keep the same model running
on Postgres (prod) and SQLite (tests).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db.base import Base


class Branding(Base):
    """The single white-label configuration row for this deployment."""

    __tablename__ = "branding"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Product name shown in the UI (title bar, login page, emails, …).
    app_name: Mapped[str] = mapped_column(String, nullable=False, default="Vizor")
    # Storage KEY of the uploaded logo (not a URL) — resolved to a URL on read.
    # None => no custom logo uploaded yet, so the frontend falls back to a default.
    logo_key: Mapped[str | None] = mapped_column(String, nullable=True)
    # Brand colours as CSS hex strings — the frontend maps these to theme tokens.
    primary_color: Mapped[str] = mapped_column(String, nullable=False, default="#4f46e5")
    accent_color: Mapped[str] = mapped_column(String, nullable=False, default="#0ea5e9")
    # When true, the app name is shown as the header wordmark; otherwise the header
    # keeps the default brand mark. A custom uploaded logo overrides both.
    name_in_header: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Bumped every time branding changes — handy for cache-busting on the client.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
