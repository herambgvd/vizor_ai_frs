"""Task helpers: the ``@task`` decorator + a SYNC DB session for workers.

Why a *sync* session in an otherwise-async codebase
---------------------------------------------------
The web app is async (FastAPI + asyncpg + AsyncSession). Celery workers, however,
run tasks **synchronously** — a worker process pulls a job and calls the function
in a normal (non-async) call stack. Driving an async engine from there means
spinning up an event loop per task, which is fragile and slow, and asyncpg is not
designed to be shared across such short-lived loops.

So workers use a *separate, synchronous* SQLAlchemy engine that talks to the SAME
database over a plain (blocking) driver. We derive its URL from the same
``settings.database_url`` by swapping the async driver for its sync counterpart:

    postgresql+asyncpg://…   →   postgresql://…      (psycopg2 / psycopg)
    sqlite+aiosqlite://…     →   sqlite://…          (stdlib sqlite3)

The engine/sessionmaker are built LAZILY on first use so importing this module in
the web process (which never needs the sync engine) costs nothing.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..core.config import get_settings
from .app import celery_app

# Re-export so callers can do ``from edge.tasks.base import celery_app``.
__all__ = ["celery_app", "task", "get_sync_session"]


def task(*args, **kwargs):
    """Thin passthrough to ``celery_app.task`` so scenarios import ONE symbol.

    Usage mirrors Celery exactly:

        from edge.tasks.base import task

        @task
        def do_work(x): ...

        @task(bind=True, max_retries=3)
        def flaky(self): ...
    """
    return celery_app.task(*args, **kwargs)


# Lazily-built sync engine + sessionmaker (see module docstring for the rationale).
_sync_engine: Engine | None = None
_sync_sessionmaker: sessionmaker[Session] | None = None


def _sync_database_url() -> str:
    """Convert the app's async DB URL to its synchronous-driver equivalent."""
    url = get_settings().database_url
    # Strip the async driver so a plain blocking driver is used in the worker.
    return url.replace("+asyncpg", "").replace("+aiosqlite", "")


def _get_sync_sessionmaker() -> sessionmaker[Session]:
    global _sync_engine, _sync_sessionmaker
    if _sync_sessionmaker is None:
        _sync_engine = create_engine(_sync_database_url(), pool_pre_ping=True)
        # expire_on_commit=False keeps ORM objects usable after commit, matching
        # the async sessionmaker's behaviour in db/base.py.
        _sync_sessionmaker = sessionmaker(
            _sync_engine, expire_on_commit=False, class_=Session
        )
    return _sync_sessionmaker


def get_sync_session() -> Session:
    """Return a fresh synchronous SQLAlchemy Session for use inside a Celery task.

    The CALLER owns the lifecycle — use it as a context manager and commit
    explicitly (the session does NOT auto-commit, same rule as the async path):

        with get_sync_session() as db:
            ... ; db.commit()
    """
    return _get_sync_sessionmaker()()
