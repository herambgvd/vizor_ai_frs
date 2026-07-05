"""Alembic environment (async).

The DB URL comes from VE_DATABASE_URL (via edge settings), not alembic.ini. We
import every model module so Base.metadata is complete — this powers both the
baseline migration and future `alembic revision --autogenerate` for scenarios.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from edge.core.config import get_settings
from edge.db.base import Base

# Import all model modules so their tables register on Base.metadata.
import edge.auth.models  # noqa: F401
import edge.core.audit  # noqa: F401
import edge.messaging  # noqa: F401
import edge.branding.models  # noqa: F401
import edge.reports.models  # noqa: F401

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


def run_offline():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
