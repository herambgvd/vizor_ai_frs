"""Assemble a ready-to-run scenario app with every platform-base capability.

A scenario's main.py becomes a few lines:

    from edge.app import create_base_app
    from edge.core import ModuleRegistry
    from .modules import cameras, attendance          # scenario feature modules
    registry = ModuleRegistry().register(cameras.SPEC).register(attendance.SPEC)
    app = create_base_app(registry, title="Vizor FRS")

create_base_app mounts the always-on platform routers (auth, licensing, storage
file-serving, audit, system, messaging, branding, reports, realtime hub), then the
license-gated feature modules from the registry.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, FastAPI

from .core import ModuleRegistry, create_app


def base_routers() -> list[APIRouter]:
    """Every always-on platform router. Imported lazily to keep import order clean."""
    from .auth import router as auth_router
    from .branding import router as branding_router
    from .core.audit import audit_router
    from .core.realtime import realtime_router
    from .core.storage import files_router
    from .licensing import router as licensing_router
    from .messaging import router as messaging_router
    from .reports import router as reports_router
    from .search import router as search_router
    from .settings import router as settings_router
    from .system import system_router

    return [
        auth_router,
        licensing_router,
        files_router,
        audit_router,
        system_router,
        messaging_router,
        branding_router,
        reports_router,
        settings_router,
        search_router,
        realtime_router,
    ]


def create_base_app(
    registry: ModuleRegistry | None = None,
    *,
    title: str = "Vizor Edge App",
    extra_routers: Iterable[APIRouter] = (),
    lifespan=None,
) -> FastAPI:
    registry = registry if registry is not None else ModuleRegistry()
    return create_app(
        registry,
        title=title,
        extra_routers=[*base_routers(), *extra_routers],
        lifespan=lifespan,
    )
