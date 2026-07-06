"""Object storage abstraction — one interface, swappable backends.

Every scenario needs to persist *blobs*: uploaded logos, report exports, face
crops, camera snapshots, recorded clips. Where those bytes actually live differs
per deployment (a local disk in dev/on-prem, an S3/MinIO bucket in the cloud), so
the app code should NEVER care. It talks to the abstract ``Storage`` interface;
``get_storage()`` picks the concrete backend from config.

Contract (this is a PINNED interface — other modules import and rely on it):

    storage = get_storage()
    key = await storage.put("logos/acme.png", data, content_type="image/png")
    raw = await storage.get(key)
    ok  = await storage.exists(key)
    href = await storage.url(key)          # a link the browser can fetch
    await storage.delete(key)

A "key" is a logical path *within* the store (e.g. ``"crops/2026/07/abc.jpg"``),
never an absolute filesystem path. The backend maps the key to a real location.

Two backends ship here:
  * LocalStorage — writes under ``settings.storage_local_dir``; URLs point back at
    this app's ``GET /files/{key}`` route (see ``files_router`` below).
  * S3Storage    — talks to AWS S3 or any S3-compatible store (MinIO). Its heavy
    dependency (``aioboto3``) is imported LAZILY inside methods so the boilerplate
    installs and runs without it when you only use the local backend.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import mimetypes

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from .config import get_settings
from .errors import NotFoundError
from .logging import get_logger

log = get_logger("edge.storage")


def _encrypts(key: str) -> bool:
    """Whether ``key`` falls under a configured encrypt-at-rest media prefix."""
    prefixes = get_settings().encrypt_media_prefixes or []
    k = key.lstrip("/")
    return any(k.startswith(p) for p in prefixes)


def _enc(key: str, data: bytes) -> bytes:
    """Encrypt on write if the key is a protected (biometric) media prefix."""
    if _encrypts(key):
        from .secrets import encrypt_bytes

        return encrypt_bytes(data)
    return data


def _dec(key: str, data: bytes) -> bytes:
    """Decrypt on read for protected keys (lenient: legacy plaintext passes through)."""
    if _encrypts(key):
        from .secrets import decrypt_bytes

        return decrypt_bytes(data)
    return data


class StorageError(Exception):
    """Raised for backend-level failures (S3 down, permission denied, etc.).

    Kept a plain ``Exception`` (not an ``AppError``) on purpose: storage failures
    are infrastructure problems, so they surface as a generic 500 via the global
    handler rather than a client-facing 4xx. Callers that want a nicer message can
    catch this and re-raise an AppError.
    """


class Storage(ABC):
    """The abstract blob store. All methods are async so an S3 backend never
    blocks the event loop. ``key`` is always a logical path within the store."""

    @abstractmethod
    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store ``data`` under ``key``; return the key (echoed for convenience)."""

    @abstractmethod
    async def get(self, key: str) -> bytes:
        """Read the blob back. Raise NotFoundError if the key does not exist."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Remove the blob. Idempotent — deleting a missing key is not an error."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """True if a blob is stored under ``key``."""

    @abstractmethod
    async def url(self, key: str, expires: int = 3600) -> str:
        """Return a URL a browser can GET. For S3 this is a presigned link that
        expires after ``expires`` seconds; for local it is a stable app URL."""


# --- Local filesystem backend ------------------------------------------------
class LocalStorage(Storage):
    """Stores blobs as plain files under ``settings.storage_local_dir``.

    Great for dev and single-node on-prem. The key becomes a relative path under
    the root, so ``put("a/b/c.png", ...)`` writes ``<root>/a/b/c.png`` (parent
    directories are created as needed).
    """

    def __init__(self) -> None:
        settings = get_settings()
        # Resolve once so every call shares the same root directory.
        self._root = Path(settings.storage_local_dir)
        self._base_url = settings.storage_base_url

    def _path(self, key: str) -> Path:
        """Map a logical key to an on-disk path, guarding against path escapes.

        A malicious key like ``"../../etc/passwd"`` must never resolve outside the
        storage root. We normalise the joined path and verify it stays inside.
        """
        # Strip any leading slash so the key is always treated as relative.
        safe_key = key.lstrip("/")
        full = (self._root / safe_key).resolve()
        root = self._root.resolve()
        if root != full and root not in full.parents:
            raise StorageError(f"key escapes storage root: {key!r}")
        return full

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        path = self._path(key)
        # Create the parent directory tree (e.g. crops/2026/07/) if absent.
        path.parent.mkdir(parents=True, exist_ok=True)
        # Filesystem writes are quick + local, so a plain sync write is fine here;
        # content_type is irrelevant on disk (it's inferred at serve time).
        # Protected (biometric) keys are encrypted at rest before hitting disk.
        path.write_bytes(_enc(key, data))
        log.debug("local put %s (%d bytes)", key, len(data))
        return key

    async def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise NotFoundError(f"object not found: {key}")
        return _dec(key, path.read_bytes())

    async def delete(self, key: str) -> None:
        path = self._path(key)
        # Idempotent: missing_ok swallows the "already gone" case.
        path.unlink(missing_ok=True)
        log.debug("local delete %s", key)

    async def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    async def url(self, key: str, expires: int = 3600) -> str:
        # Local files are served by this app's files_router; the link is stable
        # (no expiry concept on disk), so ``expires`` is ignored here.
        return f"{self._base_url.rstrip('/')}/{key.lstrip('/')}"


# --- S3 / S3-compatible backend ----------------------------------------------
class S3Storage(Storage):
    """Stores blobs in an S3 bucket (AWS or any S3-compatible store like MinIO).

    ``aioboto3`` is imported lazily inside each method so it stays an OPTIONAL
    dependency: deployments using only LocalStorage need not install it.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._endpoint = settings.s3_endpoint       # None => real AWS
        # Browser-reachable host for presigned URLs. The backend talks to S3 over the
        # INTERNAL endpoint (e.g. http://vizor-rustfs:9000), which a browser can't
        # resolve. When set, presigned links are rewritten to this public host.
        self._public_endpoint = settings.s3_public_endpoint
        self._region = settings.s3_region
        self._bucket = settings.s3_bucket
        self._access_key = settings.s3_access_key
        self._secret_key = settings.s3_secret_key
        if not self._bucket:
            raise StorageError("storage_backend=s3 but VE_S3_BUCKET is not set")
        # Set once the bucket's existence has been confirmed/created, so the
        # head+create dance happens at most once per process (see _ensure_bucket).
        self._bucket_ready = False

    def _client(self, *, presign: bool = False):
        """Build an aioboto3 S3 client context manager (used as ``async with``).

        Lazily imports aioboto3 so the import cost/dependency is only paid when
        S3 is actually configured. ``presign=True`` targets the browser-reachable
        endpoint so generated URLs work outside the docker network.
        """
        try:
            import aioboto3  # optional dependency
            from botocore.config import Config
        except ImportError as exc:  # pragma: no cover - depends on env
            raise StorageError(
                "S3Storage requires the 'aioboto3' package (pip install aioboto3)"
            ) from exc

        # SigV4 + path-style addressing: what RustFS / MinIO expect. Without this
        # botocore emits SigV2 presigned URLs (AWSAccessKeyId/Signature/Expires),
        # which RustFS rejects with 403.
        cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})
        # For presigning, sign against the BROWSER-reachable host so the SigV4 host
        # binding matches the request the browser actually makes.
        endpoint = (self._public_endpoint or self._endpoint) if presign else self._endpoint
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=endpoint,
            region_name=self._region,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=cfg,
        )

    async def _ensure_bucket(self, s3) -> None:
        """Make sure the target bucket exists, creating it on first miss.

        Idempotent + cheap after the first success: a process-level flag short-
        circuits the check so we only pay the head/create round-trip once. On a
        404 / NoSuchBucket we create the bucket. RustFS, MinIO, and AWS S3 all
        support head_bucket + create_bucket, so this works across every backend
        (a fresh MinIO/RustFS volume typically has no buckets yet — this is what
        auto-provisions the one we were configured to use).
        """
        if self._bucket_ready:
            return
        try:
            await s3.head_bucket(Bucket=self._bucket)
        except Exception as exc:  # 404 / NoSuchBucket => create it
            # Only treat "missing" as create-able; anything else (e.g. 403 access
            # denied) is a real error we shouldn't paper over.
            msg = str(exc)
            if "404" in msg or "NoSuchBucket" in msg or "Not Found" in msg:
                try:
                    await s3.create_bucket(Bucket=self._bucket)
                    log.info("s3 auto-created bucket %s", self._bucket)
                except Exception as create_exc:  # racing creator, or real failure
                    # A concurrent creator may have won the race; tolerate the
                    # "already exists / owned by you" case, re-raise anything else.
                    cmsg = str(create_exc)
                    if "BucketAlreadyOwnedByYou" not in cmsg and "BucketAlreadyExists" not in cmsg:
                        raise StorageError(
                            f"failed to create bucket {self._bucket!r}: {create_exc}"
                        ) from create_exc
            else:
                raise StorageError(f"cannot access bucket {self._bucket!r}: {exc}") from exc
        self._bucket_ready = True

    async def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        async with self._client() as s3:
            # Guarantee the bucket exists before the first write (idempotent).
            await self._ensure_bucket(s3)
            # Protected (biometric) keys are app-encrypted before upload; this is
            # defence-in-depth on top of any bucket-level SSE.
            await s3.put_object(Bucket=self._bucket, Key=key, Body=_enc(key, data), **extra)
        log.debug("s3 put %s (%d bytes)", key, len(data))
        return key

    async def get(self, key: str) -> bytes:
        async with self._client() as s3:
            try:
                resp = await s3.get_object(Bucket=self._bucket, Key=key)
            except Exception as exc:  # botocore ClientError (NoSuchKey) etc.
                # Normalise a missing object into our standard NotFoundError.
                if "NoSuchKey" in str(exc) or "404" in str(exc):
                    raise NotFoundError(f"object not found: {key}") from exc
                raise StorageError(str(exc)) from exc
            # get_object returns a streaming body; read it fully into memory.
            async with resp["Body"] as body:
                return await body.read()

    async def delete(self, key: str) -> None:
        async with self._client() as s3:
            # S3 delete_object is already idempotent (no error on missing key).
            await s3.delete_object(Bucket=self._bucket, Key=key)
        log.debug("s3 delete %s", key)

    async def exists(self, key: str) -> bool:
        async with self._client() as s3:
            try:
                await s3.head_object(Bucket=self._bucket, Key=key)
                return True
            except Exception:  # 404 / NoSuchKey => not present
                return False

    async def url(self, key: str, expires: int = 3600) -> str:
        # Encrypt-at-rest (biometric) media CANNOT be served straight from the bucket
        # — a presigned link would hand the browser ciphertext. Route those through
        # the backend proxy (/files), which fetches from S3 and decrypts in memory.
        if _encrypts(key):
            base = get_settings().storage_base_url.rstrip("/")
            return f"{base}/{key.lstrip('/')}"
        # Plain media keeps the efficient direct link. Presign against the
        # browser-reachable host (SigV4 binds the host into the signature, so it must
        # match the request the browser makes).
        async with self._client(presign=True) as s3:
            return await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires,
            )


@lru_cache
def get_storage() -> Storage:
    """Return the configured storage backend (cached singleton).

    Chosen by ``settings.storage_backend`` ("local" | "s3"). Cached because the
    backend holds config that never changes at runtime and building it repeatedly
    is wasteful.
    """
    backend = get_settings().storage_backend.lower()
    if backend == "s3":
        return S3Storage()
    if backend == "local":
        return LocalStorage()
    raise StorageError(f"unknown storage_backend: {backend!r} (use 'local' or 's3')")


# --- Local file serving route ------------------------------------------------
# Mounted by the app so that LocalStorage URLs (``/files/<key>``) actually resolve.
# For the S3 backend this route is unused (URLs point straight at the bucket).
files_router = APIRouter()


@files_router.get("/files/{key:path}")
async def serve_local_file(key: str):
    """Stream a blob stored by the LOCAL backend.

    Uses ``{key:path}`` so slashes in the key (``crops/2026/x.jpg``) are captured.
    Returns a 404 (via NotFoundError) if the file is missing. Only meaningful for
    the local backend — S3 deployments serve blobs directly from the bucket.

    Protected (encrypt-at-rest) keys can't be streamed raw off disk — they're read
    through the backend so they're decrypted in memory before reaching the client.
    """
    storage = get_storage()
    ctype = mimetypes.guess_type(key)[0] or "application/octet-stream"
    if isinstance(storage, LocalStorage):
        path = storage._path(key)  # reuse the same escape-safe key→path mapping
        if not path.is_file():
            raise NotFoundError(f"object not found: {key}")
        if _encrypts(key):
            # Decrypt in memory; never hand the browser the ciphertext on disk.
            return Response(content=_dec(key, path.read_bytes()), media_type=ctype)
        # FileResponse streams the file efficiently and infers the Content-Type.
        return FileResponse(os.fspath(path), media_type=ctype)
    # S3 (or other remote) backend: encrypt-at-rest media is proxied here so it can
    # be decrypted in memory before reaching the client (a direct bucket URL would
    # serve ciphertext). Plain media uses direct presigned URLs and never hits this.
    raw = await storage.get(key)
    return Response(content=_dec(key, raw), media_type=ctype)
