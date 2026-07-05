#!/usr/bin/env python3
"""Ensure this scenario's Postgres database exists on the SHARED server.

In standalone mode the postgres container auto-creates its POSTGRES_DB on first
boot. In shared-infra mode the one shared server only owns its own maintenance
DB, so each scenario must create its database before `alembic upgrade`. This
script parses VE_DATABASE_URL, connects to the `postgres` maintenance DB, and
creates the target database if it is missing. Idempotent + waits for the server
to accept connections (shared infra may still be starting).

Only used by docker-compose.shared.yml — the standalone compose never calls it.
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import unquote, urlsplit

import asyncpg


def _parse(dsn: str) -> dict:
    # Strip the SQLAlchemy driver suffix (postgresql+asyncpg://) → plain postgres://
    scheme = dsn.split("://", 1)[0]
    plain = dsn.replace(f"{scheme}://", "postgres://", 1)
    u = urlsplit(plain)
    if not u.path or u.path == "/":
        raise SystemExit("VE_DATABASE_URL has no database name")
    return {
        "host": u.hostname or "localhost",
        "port": u.port or 5432,
        "user": unquote(u.username) if u.username else "postgres",
        "password": unquote(u.password) if u.password else None,
        "dbname": u.path.lstrip("/"),
    }


async def _ensure(cfg: dict, attempts: int = 30) -> None:
    last: Exception | None = None
    for i in range(attempts):
        try:
            conn = await asyncpg.connect(
                host=cfg["host"], port=cfg["port"], user=cfg["user"],
                password=cfg["password"], database="postgres",
            )
            break
        except Exception as exc:  # noqa: BLE001 — server may still be booting
            last = exc
            print(f"  waiting for postgres ({i + 1}/{attempts})…", flush=True)
            await asyncio.sleep(2)
    else:
        raise SystemExit(f"cannot reach postgres: {last}")

    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", cfg["dbname"])
        if exists:
            print(f"  database {cfg['dbname']!r} already exists")
        else:
            # Identifier can't be parameterized; dbname comes from our own env, not user input.
            await conn.execute(f'CREATE DATABASE "{cfg["dbname"]}"')
            print(f"  created database {cfg['dbname']!r}")
    finally:
        await conn.close()


def main() -> int:
    dsn = os.environ.get("VE_DATABASE_URL")
    if not dsn:
        print("VE_DATABASE_URL not set — skipping ensure_db", file=sys.stderr)
        return 0
    asyncio.run(_ensure(_parse(dsn)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
