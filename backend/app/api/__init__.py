"""FRS domain API — CRUD routers mounted always-on (not license-gated).

Importing this package also registers the FRS permission catalog (via
..domain.permissions) so the role editor knows the new keys. Feature routers are
added to ``domain_routers()`` as they are ported.
"""

from ..domain import permissions as _perms  # noqa: F401 — registers FRS perms on import
from .cameras import router as cameras_router
from .events import feedback_router, router as events_router
from .groups import router as groups_router
from .ingest import router as ingest_router
from .live import router as live_router
from .investigate import router as investigate_router
from .persons import router as persons_router
from .photos import router as photos_router
from .public import router as public_router
from .reports import router as reports_router
from .settings import router as settings_router
from .transit import router as transit_router
from .tts import router as tts_router


def domain_routers():
    """Every FRS domain CRUD router, for create_base_app(extra_routers=...)."""
    return [
        groups_router, persons_router, photos_router, investigate_router, transit_router,
        reports_router, settings_router, ingest_router, public_router, tts_router,
        cameras_router, events_router, feedback_router, live_router,
    ]


__all__ = ["domain_routers"]
