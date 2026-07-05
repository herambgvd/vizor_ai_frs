"""The license-expiry gate: a validly-signed but expired license blocks feature
routes with LICENSE_EXPIRED while health stays reachable. Builds its own app with
an explicit Settings (independent of the shared test app)."""

import datetime as dt

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from edge.core import ModuleRegistry, create_app
from edge.core.config import Settings


def _signed(days: int):
    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    now = dt.datetime.now(dt.timezone.utc)
    token = jwt.encode(
        {"client": "T", "iat": now, "exp": now + dt.timedelta(days=days), "modules": [], "limits": {}},
        priv_pem,
        algorithm="EdDSA",
    )
    return token, pub_pem


def test_expired_license_blocks_features():
    token, pub = _signed(-1)
    settings = Settings(
        env="prod",
        license_token=token,
        license_public_key=pub,
        jwt_secret="x" * 32,
        secrets_key="k",
    )
    app = create_app(ModuleRegistry(), settings=settings)

    @app.get("/api/v1/thing")
    def thing():
        return {"ok": True}

    c = TestClient(app)
    assert c.get("/health").status_code == 200  # allowlisted
    r = c.get("/api/v1/thing")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "LICENSE_EXPIRED"


def test_valid_license_allows_features():
    token, pub = _signed(365)
    settings = Settings(
        env="prod",
        license_token=token,
        license_public_key=pub,
        jwt_secret="x" * 32,
        secrets_key="k",
    )
    app = create_app(ModuleRegistry(), settings=settings)

    @app.get("/api/v1/thing")
    def thing():
        return {"ok": True}

    c = TestClient(app)
    assert c.get("/api/v1/thing").status_code == 200
