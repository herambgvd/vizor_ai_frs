"""FRS feature-module registry.

The edge base (auth, branding, license, messaging, reports, system, audit, ...) is
always mounted by create_base_app. Here we register FRS's OWN feature modules —
each a self-contained package under app/modules/<id>/ with a ModuleSpec — which the
license then enables/disables per client.

Nothing is registered yet: we finish the shared EDGE UI first, then add the FRS
domain (cameras, POIs/watchlists, events) + feature modules (attendance, transit,
investigations).
"""

from __future__ import annotations

from edge.core import ModuleRegistry


def build_registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    # FRS feature modules will be registered here, e.g.:
    #   from .modules import attendance, transit, investigations
    #   registry.register(attendance.SPEC).register(transit.SPEC).register(investigations.SPEC)
    return registry
