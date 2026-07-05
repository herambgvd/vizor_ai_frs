"""Liveness / readiness endpoints.

``/health`` = process is up (for load balancers).
``/ready``  = dependencies are actually reachable (DB, Redis, storage). Returns 503
              with a per-dependency breakdown when something is down, so orchestrators
              (k8s) don't route traffic to an instance that can't serve.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .config import get_settings
from .logging import get_logger

router = APIRouter()
log = get_logger("edge.health")


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


async def _check_database() -> str:
    from sqlalchemy import text

    from ..db.base import get_sessionmaker

    async with get_sessionmaker()() as session:
        await session.execute(text("SELECT 1"))
    return "ok"


async def _check_redis() -> str:
    import redis.asyncio as aioredis

    client = aioredis.from_url(get_settings().redis_url)
    try:
        await client.ping()
        return "ok"
    finally:
        await client.aclose()


async def _check_storage() -> str:
    from .storage import get_storage

    # Cheap reachability probe: existence check on a sentinel key (never created).
    await get_storage().exists("__readyz__")
    return "ok"


async def run_checks() -> tuple[bool, dict[str, str]]:
    """Probe every dependency. Returns (all_healthy, {name: "ok" | "error: …"})."""
    checks: dict[str, str] = {}
    healthy = True
    for name, probe in (
        ("database", _check_database),
        ("redis", _check_redis),
        ("storage", _check_storage),
    ):
        try:
            checks[name] = await probe()
        except Exception as exc:  # noqa: BLE001 — report, don't crash readiness
            checks[name] = f"error: {exc}"
            healthy = False
            log.warning("dependency check failed: %s → %s", name, exc)
    return healthy, checks


@router.get("/ready")
async def ready():
    healthy, checks = await run_checks()
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
