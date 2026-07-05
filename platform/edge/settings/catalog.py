"""The catalog of admin-editable system settings.

A single, declarative source of truth: each entry describes one setting (its key,
type, default, group, and whether it is safe to expose publicly). The API returns
this catalog so the frontend renders the settings form generically — add a setting
here and it shows up in the UI with no extra frontend work.

Settings live in the ``app_settings`` table as JSON values; anything not stored
falls back to the ``default`` below.
"""

from __future__ import annotations

# type: "bool" | "text" | "number"
CATALOG: list[dict] = [
    {
        "key": "announcement",
        "type": "text",
        "default": "",
        "group": "General",
        "label": "Announcement banner",
        "description": "Shown as a banner to every signed-in user. Leave empty to hide.",
        "public": True,
    },
    {
        "key": "support_email",
        "type": "text",
        "default": "",
        "group": "General",
        "label": "Support email",
        "description": "Contact address shown in the footer and system emails.",
        "public": True,
    },
    {
        "key": "allow_avatar_uploads",
        "type": "bool",
        "default": True,
        "group": "Features",
        "label": "Allow profile photos",
        "description": "Let users upload a profile picture.",
        "public": True,
    },
    {
        "key": "allow_signups",
        "type": "bool",
        "default": False,
        "group": "Features",
        "label": "Open sign-ups",
        "description": "Reserved for scenarios that expose public self-registration.",
        "public": True,
    },
    {
        "key": "audit_retention_days",
        "type": "number",
        "default": 0,
        "group": "Data retention",
        "label": "Audit log retention (days)",
        "description": "Automatically delete audit entries older than this. 0 keeps them forever.",
        "public": False,
    },
]

_BY_KEY = {item["key"]: item for item in CATALOG}


def defaults() -> dict:
    """The default value for every catalog key."""
    return {item["key"]: item["default"] for item in CATALOG}


def public_keys() -> set[str]:
    """Keys safe to serve to unauthenticated clients (banner, flags, …)."""
    return {item["key"] for item in CATALOG if item.get("public")}


def known_keys() -> set[str]:
    return set(_BY_KEY)
