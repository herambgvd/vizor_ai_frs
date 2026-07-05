"""Reference scenario app = the platform base with no feature modules yet.

Run locally:   uvicorn example.main:app --reload
In Docker:     see ../docker-compose.yml (migrations run first, then this app).

The lifespan bootstraps the first admin from VE_BOOTSTRAP_ADMIN_EMAIL/PASSWORD
(only if the users table is empty). Copy this file into a real scenario, register
its feature modules, and you have a full app.
"""

from contextlib import asynccontextmanager

from edge.app import create_base_app
from edge.auth.service import AuthService
from edge.core.config import get_settings
from edge.core.logging import get_logger
from edge.db.base import get_sessionmaker

log = get_logger("example")


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
    yield


app = create_base_app(title="Vizor Edge (reference)", lifespan=lifespan)
