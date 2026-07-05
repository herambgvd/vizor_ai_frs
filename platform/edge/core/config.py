"""Application settings.

All config comes from environment variables (prefix ``VE_``) or a ``.env`` file.
Never hardcode secrets or endpoints in code — that's the whole point of this file.

Example .env:
    VE_ENV=prod
    VE_DATABASE_URL=postgresql+asyncpg://vizor:secret@db:5432/frs
    VE_QDRANT_URL=http://qdrant:6333
    VE_LICENSE_TOKEN_FILE=/etc/vizor/license.jwt
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VE_", env_file=".env", extra="ignore")

    # Runtime environment. "dev" enables a permissive license fallback (see license.py).
    env: str = "dev"
    app_name: str = "vizor-edge-app"

    # --- API ---------------------------------------------------------------
    # All versioned routers mount under this prefix (bump to /api/v2 for a new version).
    api_prefix: str = "/api/v1"

    # --- Security policy ---------------------------------------------------
    password_min_length: int = 8
    password_require_number: bool = True
    password_require_letter: bool = True
    rate_limit_login_per_minute: int = 10
    # Global per-IP request cap across the whole API (0 disables it). A coarse
    # brute-force / abuse backstop on top of the stricter per-login limit.
    rate_limit_global_per_minute: int = 600
    # Per-ACCOUNT brute-force lockout (complements the per-IP limit). Lock after
    # this many consecutive failed logins, for this many minutes (0 disables).
    lockout_max_attempts: int = 5
    lockout_minutes: int = 15
    # Password lifecycle. expiry_days=0 disables expiry; history_count blocks
    # reuse of the last N password hashes.
    password_expiry_days: int = 0
    password_history_count: int = 5

    # --- Biometric / sensitive-media protection (STQC / DPDP) --------------
    # Object keys under any of these prefixes are transparently encrypted at rest
    # (Fernet, keyed from secrets_key) and decrypted on read/serve. Empty = off.
    # Default protects the FRS biometric media tree (enrollment faces, crops).
    encrypt_media_prefixes: list[str] = ["frs/"]
    # Auto-purge recognition appearances older than this many days (0 = keep
    # forever). Enforced by the retention beat task + the manual purge endpoint.
    appearance_retention_days: int = 0

    # --- Databases ---------------------------------------------------------
    database_url: str = "postgresql+asyncpg://vizor:vizor@localhost:5432/vizor"
    # Vector DB is OPTIONAL — only scenarios that match by embedding set this.
    qdrant_url: str | None = None
    # Redis — Celery broker/result backend + realtime pub/sub.
    redis_url: str = "redis://localhost:6379/0"
    # MediaMTX control API (camera path register / republish / record).
    mediamtx_url: str = "http://localhost:9997"

    # --- App auth (the app's own users, NOT the license) -------------------
    jwt_secret: str = "change-me-in-prod"
    jwt_ttl_minutes: int = 60 * 12

    # Key used to derive the Fernet cipher that encrypts integration secrets
    # (SMTP / FCM / S3 credentials) stored in the DB. Rotate to re-key.
    secrets_key: str = "change-me-secret"

    # First-run bootstrap: if set and the users table is empty, the app creates
    # this admin (with the built-in Administrator role) on startup.
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None

    # --- Licensing (see core/license.py) -----------------------------------
    # Provide the token inline OR via a file; same for the verification public key.
    license_token: str | None = None
    license_token_file: str | None = None
    license_public_key: str | None = None
    license_public_key_file: str | None = "license_pub.pem"

    # --- Models ------------------------------------------------------------
    model_dir: str = "./models"
    # Inference device for the ONNX runtime: "cpu" (default, portable) or "cuda"
    # (NVIDIA GPU via onnxruntime-gpu). On "cuda" the runtime uses the CUDA
    # execution provider with a CPU fallback, so a missing GPU degrades safely.
    inference_device: str = "cpu"

    # --- Liveness / presentation-attack detection (PAD, ISO/IEC 30107) -----
    # Anti-spoofing. When enabled AND a PAD model is present at {model_dir}/pad,
    # enrolment (and, later, the live pipeline) score face liveness and reject
    # presentation attacks (printed photo, screen replay) below pad_threshold.
    pad_enabled: bool = False
    pad_threshold: float = 0.5
    # If the model is MISSING while pad_enabled, fail OPEN (allow + warn) rather
    # than brick enrolment. Set true to fail CLOSED (block until a model is added).
    pad_block_when_unavailable: bool = False

    # --- Object storage (logos, exports, crops, snapshots, clips) ----------
    # Public base URL of the frontend — used to build links inside emails
    # (invites, password resets). Set to the real domain in production.
    frontend_url: str = "http://localhost:3000"
    storage_backend: str = "local"            # "local" | "s3"
    storage_local_dir: str = "./data/storage"
    storage_base_url: str = "/files"          # public URL prefix for local files
    s3_endpoint: str | None = None            # e.g. http://minio:9000 (None = AWS)
    s3_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_access_key: str | None = None
    s3_secret_key: str | None = None

    # --- CORS (frontend origins) ------------------------------------------
    cors_origins: list[str] = ["http://localhost:3000"]
    # Regex of allowed origins. Default allows ANY http(s) origin so the app opens
    # from localhost or any machine/IP on the LAN without friction (the specific
    # origin is echoed back, so it stays compatible with allow_credentials=True).
    # Tighten this in production by overriding VE_CORS_ORIGIN_REGEX (or cors_origins).
    cors_origin_regex: str = r"https?://.*"


@lru_cache
def get_settings() -> Settings:
    """Cached singleton so we parse the environment only once."""
    return Settings()
