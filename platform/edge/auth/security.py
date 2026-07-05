"""Password hashing, JWT tokens, and API-key generation — the crypto primitives.

- Passwords: argon2id (OWASP-recommended). Never store or log the plaintext.
- Tokens: short-lived ACCESS + long-lived REFRESH, signed HS256 with ``VE_JWT_SECRET``.
  Claims are minimal — sub (user id), type, iat, exp. Permissions are NOT baked into
  the token; they're loaded fresh from the user's role each request, so a permission
  change takes effect immediately (no stale token).
- API keys: high-entropy ``vz_...`` string; only its SHA-256 hash is stored.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import secrets as pysecrets
import struct
import time
import urllib.parse

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from ..core.config import get_settings
from ..core.errors import ValidationError

_ph = PasswordHasher()

REFRESH_TTL = dt.timedelta(days=30)


# --- Passwords -------------------------------------------------------------
def hash_password(plaintext: str) -> str:
    return _ph.hash(plaintext)


def verify_password(plaintext: str, hashed: str) -> bool:
    try:
        _ph.verify(hashed, plaintext)
        return True
    except VerifyMismatchError:
        return False


def validate_password(password: str) -> None:
    """Enforce the configured password policy; raise ValidationError if it fails."""
    s = get_settings()
    if len(password) < s.password_min_length:
        raise ValidationError(f"password must be at least {s.password_min_length} characters")
    if s.password_require_number and not any(c.isdigit() for c in password):
        raise ValidationError("password must contain at least one number")
    if s.password_require_letter and not any(c.isalpha() for c in password):
        raise ValidationError("password must contain at least one letter")


# --- JWT -------------------------------------------------------------------
def _encode(
    sub, token_type: str, ttl: dt.timedelta, jti: str | None = None, sid: str | None = None
) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(sub), "type": token_type, "iat": now, "exp": now + ttl}
    if jti is not None:
        payload["jti"] = jti  # ties a refresh token to a revocable DB row
    if sid is not None:
        payload["sid"] = sid  # ties an access token to its originating session
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def create_access_token(user, sid: str | None = None) -> str:
    ttl = dt.timedelta(minutes=get_settings().jwt_ttl_minutes)
    return _encode(user.id, "access", ttl, sid=sid)


def create_refresh_token(user, jti: str) -> str:
    return _encode(user.id, "refresh", REFRESH_TTL, jti=jti)


# --- Two-factor (TOTP, RFC 6238) + MFA challenge token ---------------------
MFA_CHALLENGE_TTL = dt.timedelta(minutes=5)


def create_mfa_challenge_token(user) -> str:
    """Short-lived token proving the FIRST factor passed; exchanged for real
    tokens once the user submits a valid TOTP/recovery code."""
    return _encode(user.id, "mfa", MFA_CHALLENGE_TTL)


def generate_totp_secret() -> str:
    """A fresh base32 TOTP secret (160 bits, no padding) for an authenticator app."""
    return base64.b32encode(pysecrets.token_bytes(20)).decode().rstrip("=")


def totp_provisioning_uri(secret_b32: str, account: str, issuer: str) -> str:
    """otpauth:// URI the client renders as a QR code for Google Authenticator etc."""
    label = urllib.parse.quote(f"{issuer}:{account}")
    query = urllib.parse.urlencode(
        {"secret": secret_b32, "issuer": issuer, "algorithm": "SHA1", "digits": 6, "period": 30}
    )
    return f"otpauth://totp/{label}?{query}"


def _hotp(secret_b32: str, counter: int, digits: int = 6) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def verify_totp(secret_b32: str, code: str, *, window: int = 1, period: int = 30) -> bool:
    """Validate a 6-digit TOTP, tolerating +/- ``window`` steps of clock drift."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    counter = int(time.time() // period)
    return any(
        hmac.compare_digest(_hotp(secret_b32, counter + drift), code)
        for drift in range(-window, window + 1)
    )


def normalize_recovery_code(code: str) -> str:
    return (code or "").strip().replace(" ", "").lower()


def generate_recovery_codes(n: int = 10) -> tuple[list[str], list[str]]:
    """Return (raw_codes, hashed_codes). Show raw once; store only the hashes."""
    raw = [f"{pysecrets.token_hex(2)}-{pysecrets.token_hex(2)}" for _ in range(n)]
    return raw, [hash_api_key(normalize_recovery_code(c)) for c in raw]


def generate_reset_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Email the raw; store the hash."""
    raw = pysecrets.token_urlsafe(32)
    return raw, hash_api_key(raw)


def decode_token(token: str) -> dict:
    """Decode + verify signature/expiry. Raises jwt.PyJWTError on failure."""
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


# --- API keys --------------------------------------------------------------
def generate_api_key() -> tuple[str, str, str]:
    """Return (raw_key, prefix, sha256_hash). Show raw_key once; store the rest."""
    raw = "vz_" + pysecrets.token_urlsafe(32)
    return raw, raw[:11], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
