"""Branding: white-label identity (app name, logo, brand colours) for a deployment.

Single-row config. Read is PUBLIC (the login page themes itself); management is
gated by ``CorePerm.BRANDING_MANAGE``.

Wire into a scenario app:

    from edge import branding
    app = create_app(registry, extra_routers=[branding.router])
"""

from .models import Branding
from .router import router

__all__ = ["router", "Branding"]
