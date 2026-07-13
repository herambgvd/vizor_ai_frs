"""Alembic env (async) for the FRS backend.

Imports the shared EDGE model modules (so their tables are created here) plus any
FRS-owned models. Both inherit edge.db.base.Base, so a single metadata covers the
whole schema.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from edge.core.config import get_settings
from edge.db.base import Base

# Edge base tables
import edge.auth.models  # noqa: F401
import edge.core.audit  # noqa: F401
import edge.messaging  # noqa: F401
import edge.branding.models  # noqa: F401
import edge.reports.models  # noqa: F401
import edge.settings.models  # noqa: F401 — app_settings (platform settings store)

# FRS-owned models (added as the domain is built), e.g.:
# import app.domain  # noqa: F401

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
