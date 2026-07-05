"""Pydantic request/response schemas for the branding API.

Note the asymmetry between storage and API:
  * The DB stores a ``logo_key`` (a storage path, not directly fetchable).
  * The API exposes a ``logo_url`` — a browser-fetchable link the router resolves
    from the key via ``storage.url(...)`` at response time. So there is no
    ``from_attributes`` round-trip for the logo; the router builds it explicitly.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class BrandingOut(BaseModel):
    """What the frontend consumes to theme itself. ``logo_url`` is a resolved,
    fetchable URL (or None when no logo has been uploaded)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    app_name: str
    logo_url: str | None
    primary_color: str
    accent_color: str
    name_in_header: bool


class UpdateBrandingIn(BaseModel):
    """Partial update — every field optional so a client can change just one thing
    (e.g. only the primary colour) without resending the whole object."""

    app_name: str | None = None
    primary_color: str | None = None
    accent_color: str | None = None
    name_in_header: bool | None = None
