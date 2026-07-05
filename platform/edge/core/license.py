"""Offline, tamper-proof licensing for single-tenant scenario apps.

WHY THIS DESIGN
---------------
Each deployment is one client (single-tenant). We want ONE codebase that we sell
in tiers by handing each client a different license. Requirements:
  * Offline  — must work air-gapped, no license server / phone-home.
  * Tamper-proof — the client must not be able to raise their own camera limit.

Solution: a signed JWT (Ed25519 / "EdDSA").
  * Vendor signs the license with a PRIVATE key (kept secret, see tools/gen_license.py).
  * The app bundles only the PUBLIC key and verifies the signature + expiry.
  * Editing any claim (cameras, modules, expiry) breaks the signature -> rejected.

The verified :class:`License` then gates: which feature modules load, how many
cameras can be added, storage caps, and per-feature flags.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import jwt  # PyJWT


class LicenseError(Exception):
    """Raised when a license is missing, malformed, expired, or unsigned."""


@dataclasses.dataclass(frozen=True)
class License:
    client: str
    issued_at: dt.datetime | None
    expires_at: dt.datetime | None
    modules: frozenset[str]          # enabled feature-module ids
    limits: dict                     # {"cameras": 10, "storage_gb": 500, ...}
    features: dict                   # {"age_gender": true, "export": true, ...}
    _dev: bool = False               # dev fallback => everything unlocked

    # --- Gates the rest of the app calls -----------------------------------
    def has_module(self, module_id: str) -> bool:
        return self._dev or module_id in self.modules

    def limit(self, name: str, default=None):
        return default if self._dev else self.limits.get(name, default)

    @property
    def camera_limit(self) -> int | None:
        """None means unlimited (dev, or limit simply not set)."""
        return None if self._dev else self.limits.get("cameras")

    @property
    def storage_gb(self) -> float | None:
        return None if self._dev else self.limits.get("storage_gb")

    def feature(self, name: str, default: bool = False) -> bool:
        return True if self._dev else bool(self.features.get(name, default))

    @property
    def is_expired(self) -> bool:
        if self._dev or self.expires_at is None:
            return False
        return dt.datetime.now(dt.timezone.utc) >= self.expires_at

    @classmethod
    def dev_unlimited(cls) -> "License":
        """Permissive license used only in dev when no token is configured."""
        return cls(
            client="DEV",
            issued_at=None,
            expires_at=None,
            modules=frozenset(),
            limits={},
            features={},
            _dev=True,
        )


def _to_dt(value) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def verify_license(token: str, public_key_pem: str) -> License:
    """Verify a signed license token's SIGNATURE against the vendor public key.

    An EXPIRED but validly-signed license still loads (verify_exp=False) so the app
    starts and the runtime guard can show a "License Expired" screen + let an admin
    upload a fresh token. Expiry is surfaced via License.is_expired, not by raising.
    Only a bad/absent signature (or missing exp claim) raises LicenseError.
    """
    try:
        claims = jwt.decode(
            token,
            public_key_pem,
            algorithms=["EdDSA"],
            options={"require": ["exp"], "verify_exp": False},
        )
    except jwt.PyJWTError as exc:
        raise LicenseError(f"invalid license: {exc}") from exc

    return License(
        client=claims.get("client", "unknown"),
        issued_at=_to_dt(claims.get("iat")),
        expires_at=_to_dt(claims.get("exp")),
        modules=frozenset(claims.get("modules", [])),
        limits=dict(claims.get("limits", {}) or {}),
        features=dict(claims.get("features", {}) or {}),
    )


def _read(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    return p.read_text().strip() if p.exists() else None


def load_license(settings) -> License:
    """Resolve token + public key from settings and verify.

    In dev with nothing configured we fall back to an unlimited license so the
    app runs out-of-the-box. In prod a missing/invalid license is a hard error.
    """
    token = settings.license_token or _read(settings.license_token_file)
    public_key = settings.license_public_key or _read(settings.license_public_key_file)

    if not token or not public_key:
        if settings.env == "dev":
            return License.dev_unlimited()
        raise LicenseError("no license configured (set VE_LICENSE_TOKEN[_FILE])")

    return verify_license(token, public_key)
