"""Pytest fixtures: a real app on a throwaway SQLite DB with a bootstrapped admin.

Environment is set at import time (before any `edge` import) because settings are
cached. The `client` fixture builds the reference app; `admin_headers` logs in.
"""

import asyncio
import os
import sys
import tempfile

_WORK = tempfile.mkdtemp()
os.environ.update(
    VE_ENV="dev",
    VE_DATABASE_URL=f"sqlite+aiosqlite:///{_WORK}/test.db",
    VE_JWT_SECRET="test-jwt-secret-that-is-long-enough-32b",
    VE_SECRETS_KEY="test-secrets-key",
    VE_STORAGE_LOCAL_DIR=f"{_WORK}/storage",
    VE_RATE_LIMIT_LOGIN_PER_MINUTE="1000",  # don't trip the limiter during tests
    VE_BOOTSTRAP_ADMIN_EMAIL="admin@example.com",
    VE_BOOTSTRAP_ADMIN_PASSWORD="changeme123",
)

# so `import example.main` resolves (example isn't a pip-installed package)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

API = "/api/v1"


@pytest.fixture(scope="session")
def client():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from edge.auth.service import AuthService
    from edge.db.base import Base

    # import every model module so create_all builds all tables
    import edge.auth.models  # noqa: F401
    import edge.branding.models  # noqa: F401
    import edge.core.audit  # noqa: F401
    import edge.messaging  # noqa: F401
    import edge.reports.models  # noqa: F401

    async def _setup():
        eng = create_async_engine(os.environ["VE_DATABASE_URL"])
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(eng, expire_on_commit=False)() as s:
            await AuthService(s).ensure_admin("admin@example.com", "changeme123")
        await eng.dispose()

    asyncio.run(_setup())

    import example.main as m

    with TestClient(m.app) as c:
        yield c


@pytest.fixture
def admin_headers(client):
    r = client.post(f"{API}/auth/login", json={"email": "admin@example.com", "password": "changeme123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
