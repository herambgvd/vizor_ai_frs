"""Permission catalog — the atomic access rights the CODE enforces.

Design (industry-standard RBAC):
  * PERMISSIONS are a fixed catalog. Each is a key the code checks
    (``require_permission("user.manage")``). The system/feature-modules define
    them — a user can't invent one, because nothing would enforce it.
  * ROLES are user-defined (a name + a chosen subset of these permissions),
    stored in the DB and fully CRUD. See models.Role.
  * A user is assigned a role → their effective permissions = the role's set.

Feature modules add their own permissions at import time:

    from edge.auth import PERMISSIONS, Permission
    PERMISSIONS.register(Permission("camera.create", "Add cameras", "Cameras"))

The ``*`` wildcard grants everything and is reserved for the built-in
Administrator role (not selectable when creating custom roles).
"""

from __future__ import annotations

import dataclasses

WILDCARD = "*"


@dataclasses.dataclass(frozen=True)
class Permission:
    key: str            # machine key the code checks, e.g. "user.manage"
    label: str          # human label for the role-editor UI
    group: str          # grouping bucket in the UI, e.g. "Users"
    description: str = ""


class PermissionRegistry:
    """Holds every permission the app knows about; the frontend reads it to
    render the role editor (grouped checkboxes)."""

    def __init__(self) -> None:
        self._perms: dict[str, Permission] = {}

    def register(self, *perms: Permission) -> "PermissionRegistry":
        for p in perms:
            self._perms[p.key] = p
        return self

    def all(self) -> list[Permission]:
        return list(self._perms.values())

    def keys(self) -> set[str]:
        return set(self._perms)

    def grouped(self) -> dict[str, list[dict]]:
        """{"Users": [{key,label,description}, ...], ...} for the role editor."""
        out: dict[str, list[dict]] = {}
        for p in self._perms.values():
            out.setdefault(p.group, []).append(
                {"key": p.key, "label": p.label, "description": p.description}
            )
        return out

    def unknown(self, perms) -> list[str]:
        """Return permission keys NOT in the catalog (wildcard excluded)."""
        known = self._perms.keys()
        return [p for p in perms if p != WILDCARD and p not in known]


# The single shared registry for the whole app.
PERMISSIONS = PermissionRegistry()


class CorePerm:
    """Permission keys the boilerplate itself enforces (referenced in routers)."""

    USER_READ = "user.read"
    USER_MANAGE = "user.manage"
    ROLE_READ = "role.read"
    ROLE_MANAGE = "role.manage"
    APIKEY_MANAGE = "apikey.manage"
    AUDIT_READ = "audit.read"
    BRANDING_MANAGE = "branding.manage"
    SETTINGS_MANAGE = "settings.manage"
    SYSTEM_READ = "system.read"
    REPORT_READ = "report.read"
    REPORT_EXPORT = "report.export"


PERMISSIONS.register(
    Permission(CorePerm.USER_READ, "View users", "Users"),
    Permission(CorePerm.USER_MANAGE, "Create / edit users", "Users"),
    Permission(CorePerm.ROLE_READ, "View roles", "Roles"),
    Permission(CorePerm.ROLE_MANAGE, "Create / edit roles & permissions", "Roles"),
    Permission(CorePerm.APIKEY_MANAGE, "Manage API keys", "API keys"),
    Permission(CorePerm.AUDIT_READ, "View audit log", "Audit"),
    Permission(CorePerm.BRANDING_MANAGE, "Edit branding / white-label", "Branding"),
    Permission(CorePerm.SETTINGS_MANAGE, "Edit integration settings", "Settings"),
    Permission(CorePerm.SYSTEM_READ, "View system resources", "System"),
    Permission(CorePerm.REPORT_READ, "View reports", "Reports"),
    Permission(CorePerm.REPORT_EXPORT, "Export reports", "Reports"),
)
