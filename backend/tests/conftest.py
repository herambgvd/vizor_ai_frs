"""Shared pytest fixtures for the FRS backend suite.

All tests run headless — no Triton / Qdrant / Postgres / cameras. Anything that
needs a DB uses an in-memory async SQLite engine with the ORM metadata created
fresh per test; anything that would reach Qdrant / object storage / the recogniser
is monkeypatched by the individual test.

IMPORTANT: the very first ``import app.*`` below pulls ``edge.core`` in before
``edge.db.base``. The edge boilerplate has a circular import that only bites when
``edge.db.base`` is imported *first* (models -> edge.db.base -> edge.core ->
... -> edge.db.base). Importing an app module here primes the package in the
right order so every later ``from app.domain.models import ...`` resolves.
"""

from __future__ import annotations

import app.events  # noqa: F401  — import-order primer (see module docstring)

import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.models import Base


@pytest_asyncio.fixture
async def engine():
    """A fresh in-memory SQLite engine with all FRS tables created."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(sessionmaker):
    """An open AsyncSession bound to the in-memory DB."""
    async with sessionmaker() as session:
        yield session
