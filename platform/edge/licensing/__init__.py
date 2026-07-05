"""License status + runtime update API (enterprise license gate).

Mount alongside auth:  create_app(registry, extra_routers=[auth.router, licensing.router])
The expiry ENFORCEMENT is a middleware wired in core.create_app; this package is the
status/update surface an admin uses to renew an expired license.
"""

from .router import router

__all__ = ["router"]
