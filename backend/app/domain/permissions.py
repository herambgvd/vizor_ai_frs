"""FRS domain permissions — registered into the shared catalog at import time.

Feature/scenario code declares its own permission keys so they appear in the role
editor and can gate routes. Imported by app/api so registration happens on startup.
Keys are added per feature during the port.
"""

from __future__ import annotations

from edge.auth import PERMISSIONS, Permission


class FrsPerm:
    """FRS permission keys. Extended per ported feature."""

    # Groups (watchlists)
    GROUP_READ = "frs.group.read"
    GROUP_MANAGE = "frs.group.manage"
    # Persons (gallery)
    PERSON_READ = "frs.person.read"
    PERSON_MANAGE = "frs.person.manage"
    # Events / investigations / reports
    EVENT_READ = "frs.event.read"
    EVENT_MANAGE = "frs.event.manage"
    # Transit (cross-camera movement rules)
    TRANSIT_READ = "frs.transit.read"
    TRANSIT_MANAGE = "frs.transit.manage"
    # Cameras (video sources) + live monitoring
    CAMERA_READ = "frs.camera.read"
    CAMERA_MANAGE = "frs.camera.manage"
    # Feature settings (public dashboard + ingest API)
    SETTINGS_MANAGE = "frs.settings.manage"


PERMISSIONS.register(
    Permission(FrsPerm.SETTINGS_MANAGE, "Manage FRS feature settings", "FRS · Settings"),
    Permission(FrsPerm.GROUP_READ, "View person groups", "FRS · Groups"),
    Permission(FrsPerm.GROUP_MANAGE, "Add / edit person groups", "FRS · Groups"),
    Permission(FrsPerm.PERSON_READ, "View persons", "FRS · Persons"),
    Permission(FrsPerm.PERSON_MANAGE, "Add / edit / delete persons", "FRS · Persons"),
    Permission(FrsPerm.EVENT_READ, "View events / investigate / reports", "FRS · Events"),
    Permission(FrsPerm.EVENT_MANAGE, "Purge events / manage retention", "FRS · Events"),
    Permission(FrsPerm.TRANSIT_READ, "View transit rules / sessions", "FRS · Transit"),
    Permission(FrsPerm.TRANSIT_MANAGE, "Add / edit transit rules", "FRS · Transit"),
    Permission(FrsPerm.CAMERA_READ, "View cameras / live monitoring", "FRS · Cameras"),
    Permission(FrsPerm.CAMERA_MANAGE, "Add / edit / delete cameras", "FRS · Cameras"),
)
