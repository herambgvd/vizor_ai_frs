"""TimescaleDB helpers.

Event tables (recognition_events, resource_samples, ...) are time-series: many
inserts, queried by time range. Timescale turns an ordinary table into a
**hypertable** (transparently time-partitioned into chunks) for fast range scans
and easy retention (drop old chunks).

Call ``create_hypertable`` inside an Alembic migration AFTER the table is created.
Requires the ``timescale/timescaledb`` Postgres image.
"""

from __future__ import annotations

from sqlalchemy import text


async def create_hypertable(
    conn,
    table: str,
    time_column: str = "ts",
    *,
    chunk_interval: str = "7 days",
) -> None:
    """Convert an existing table into a Timescale hypertable (idempotent).

    ``table``/``time_column`` come from our own migrations (never user input), so
    formatting them into the SQL is safe.
    """
    await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
    await conn.execute(
        text(
            f"SELECT create_hypertable('{table}', '{time_column}', "
            f"if_not_exists => TRUE, migrate_data => TRUE, "
            f"chunk_time_interval => INTERVAL '{chunk_interval}')"
        )
    )
