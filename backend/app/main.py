"""Neubit backend — the edge platform base + (later) FRS feature modules.

Run:   uvicorn app.main:app --reload
Docker: see ../docker-compose.yml (migrations run first).

For now this is the pure edge base (auth / branding / license / messaging / reports /
system / audit / realtime) so we can build and test the shared EDGE UI. FRS domain
+ feature modules get registered in app/registry.py as they're built.
"""

import asyncio
from contextlib import asynccontextmanager

from edge.app import create_base_app
from edge.auth.service import AuthService
from edge.core.config import get_settings
from edge.core.logging import get_logger
from edge.db.base import get_sessionmaker

from .registry import build_registry
from .retention import retention_sweeper_loop
from .scheduler import start_background_tasks, stop_background_tasks

log = get_logger("frs")


@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    if settings.bootstrap_admin_email and settings.bootstrap_admin_password:
        async with get_sessionmaker()() as db:
            created = await AuthService(db).ensure_admin(
                settings.bootstrap_admin_email, settings.bootstrap_admin_password
            )
            if created:
                log.info("bootstrapped first admin: %s", settings.bootstrap_admin_email)
    # FRS background daemons: report auto-send + transit overdue sweep + retention.
    # A failure to start any daemon must never crash app startup.
    tasks: list[asyncio.Task] = []
    try:
        tasks = start_background_tasks()
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to start FRS background tasks: %s", exc)
    try:
        tasks.append(asyncio.create_task(retention_sweeper_loop(), name="frs-retention"))
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to start FRS retention sweeper: %s", exc)
    try:
        yield
    finally:
        stop_background_tasks(tasks)


from .api import domain_routers  # noqa: E402 — after lifespan is defined

app = create_base_app(
    build_registry(),
    title="wonin.ai",
    extra_routers=domain_routers(),
    lifespan=lifespan,
)
