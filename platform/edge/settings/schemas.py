"""Pydantic schemas for the system-settings API."""

from __future__ import annotations

from pydantic import BaseModel


class SettingsOut(BaseModel):
    """The editable catalog + current effective values (for the admin form)."""

    catalog: list[dict]
    values: dict


class UpdateSettingsIn(BaseModel):
    """A partial map of setting key → new value (only sent keys change)."""

    values: dict
