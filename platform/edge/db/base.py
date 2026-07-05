"""Async SQLAlchemy engine, session factory, declarative Base, and the get_db dep.

Every scenario's domain models inherit from ``Base``; every route that touches the
DB depends on ``get_db`` (a per-request session, closed automatically).

IMPORTANT: the session does NOT auto-commit. A service that writes must call
``await session.commit()`` explicitly — a bare flush is rolled back on teardown.

The engine/sessionmaker are created lazily on first use so importing this module
never requires a live database (tests and tooling can import models freely).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from ..core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


class Base(DeclarativeBase):
    """Declarative base every ORM model in every scenario inherits from."""


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        # expire_on_commit=False → objects stay usable after commit (no lazy re-fetch).
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yields a session, always closes it."""
    async with get_sessionmaker()() as session:
        yield session
