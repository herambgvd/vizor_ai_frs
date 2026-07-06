"""FRS feature-module license gating.

The FRS routers stay mounted at their stable ``/frs/...`` paths, but the optional
FEATURE modules are gated per-client by the signed license: a request to a route
belonging to a non-licensed module returns 403. Under a dev / unlimited license
everything is enabled (``License.has_module`` returns True when ``_dev``), so this
is a no-op in dev and only bites in production with a limited license.

``GET /frs/modules`` reports the enabled set so the UI can hide disabled nav.

Core capture (cameras / persons / groups / photos / events / live / ingest /
settings / tts / public) is always on — only these value-add modules are gated.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from edge.core.errors import ForbiddenError

# Gateable FRS feature modules → human label.
FRS_MODULES = {
    "attendance": "Attendance",
    "transit": "Transit / tailgating",
    "investigate": "Forensic investigate & tour",
    "reports": "Reports & scheduling",
}


def require_module(key: str):
    """FastAPI dependency: allow the request only if ``key`` is licensed.

    Reads ``app.state.license`` (set by the edge app factory) on every request, so a
    license renewal takes effect immediately. Allows when unlicensed-object-missing
    (fail-open on misconfig) or when the license enables the module (always true
    under a dev/unlimited license)."""

    async def _dep(request: Request) -> None:
        lic = getattr(request.app.state, "license", None)
        if lic is None or lic.has_module(key):
            return
        raise ForbiddenError(f"the '{key}' module is not enabled for this license")

    return _dep


modules_router = APIRouter(prefix="/frs", tags=["frs-modules"])


@modules_router.get("/modules")
async def list_modules(request: Request) -> dict:
    """Which optional FRS modules the current license enables (for UI nav gating)."""
    lic = getattr(request.app.state, "license", None)
    return {
        "modules": [
            {"key": k, "label": v, "enabled": (lic.has_module(k) if lic is not None else True)}
            for k, v in FRS_MODULES.items()
        ]
    }
