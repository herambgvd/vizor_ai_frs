"""Thin client for the MediaMTX control API (v3).

MediaMTX is the single media server for the edge stack: it ingests camera RTSP,
optionally records to disk, and re-publishes each stream over RTSP / WebRTC / HLS
so browsers and downstream consumers can view it without touching the camera
directly. This module lets the app register/unregister camera "paths" and derive
the republish URLs.

We use the **synchronous** ``httpx.Client`` on purpose: path registration happens
at camera-add / camera-remove time (rare, request-scoped control-plane actions),
not on the hot frame path — so the simplicity of blocking calls beats the churn
of threading an async client through call sites. If a caller ever needs this from
async code, wrap the call in ``anyio.to_thread`` / ``run_in_executor``.

MediaMTX control API reference (v3), all under ``<base_url>/v3/``:
    POST   config/paths/add/{name}      register a path      {"source", "record"}
    DELETE config/paths/delete/{name}   unregister a path
    GET    paths/list                   list active paths
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx

from edge.core.config import get_settings
from edge.core.logging import get_logger

log = get_logger("edge.stream.mediamtx")

# Default MediaMTX republish ports (its built-in servers). Overridable per call.
_RTSP_PORT = 8554
_WEBRTC_PORT = 8889
_HLS_PORT = 8888


class MediaMTXError(RuntimeError):
    """Raised when a MediaMTX control call fails (network or non-2xx)."""


class MediaMTXClient:
    """Register camera paths and build republish URLs against MediaMTX."""

    def __init__(self, base_url: str | None = None) -> None:
        """
        Args:
            base_url: control-API root, e.g. ``http://localhost:9997``. Defaults
                to ``settings.mediamtx_url``.
        """
        self.base_url = (base_url or get_settings().mediamtx_url).rstrip("/")
        # Short timeout: the control API is local and must not stall a request.
        self._client = httpx.Client(base_url=self.base_url, timeout=10.0)
        # Host used to build republish URLs (strip scheme/port from control URL).
        self._host = urlparse(self.base_url).hostname or "localhost"

    # ------------------------------------------------------------------ helpers
    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Issue a request under ``/v3/`` and raise a clean error on failure."""
        url = f"/v3/{path.lstrip('/')}"
        try:
            resp = self._client.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as exc:
            # Surface MediaMTX's own error body — it explains *why* it rejected us.
            body = exc.response.text
            log.error("MediaMTX %s %s -> %d: %s", method, url, exc.response.status_code, body)
            raise MediaMTXError(
                f"MediaMTX {method} {url} failed ({exc.response.status_code}): {body}"
            ) from exc
        except httpx.HTTPError as exc:  # connection error, timeout, etc.
            log.error("MediaMTX %s %s transport error: %s", method, url, exc)
            raise MediaMTXError(f"MediaMTX {method} {url} transport error: {exc}") from exc

    # ------------------------------------------------------------------ paths
    def add_path(self, name: str, source: str, *, record: bool = False) -> None:
        """Register (or replace) a path that pulls from ``source``.

        Args:
            name: the path name — becomes the URL suffix (e.g. ``cam-1``).
            source: the upstream to pull, typically the camera RTSP URL. MediaMTX
                connects on demand and re-publishes it under ``name``.
            record: if True, MediaMTX also records the stream to disk per its
                recording config (segments/retention configured server-side).
        """
        payload = {"source": source, "record": record}
        log.info("MediaMTX add_path %s <- %s (record=%s)", name, source, record)
        self._request("POST", f"config/paths/add/{name}", json=payload)

    def remove_path(self, name: str) -> None:
        """Unregister a previously-added path. No-op-safe on the caller side."""
        log.info("MediaMTX remove_path %s", name)
        self._request("DELETE", f"config/paths/delete/{name}")

    def list_paths(self) -> dict[str, Any]:
        """Return MediaMTX's live path list (``{"items": [...], ...}``)."""
        resp = self._request("GET", "paths/list")
        return resp.json()

    # ------------------------------------------------------------------ urls
    def read_url(self, name: str, proto: str = "rtsp") -> str:
        """Build the republish URL a consumer uses to *read* the path.

        Args:
            name: the path name previously registered via ``add_path``.
            proto: one of ``"rtsp"``, ``"webrtc"``, or ``"hls"``.

        Returns:
            A fully-qualified URL, e.g. ``rtsp://localhost:8554/cam-1`` or
            ``http://localhost:8888/cam-1/index.m3u8`` for HLS.
        """
        proto = proto.lower()
        if proto == "rtsp":
            return f"rtsp://{self._host}:{_RTSP_PORT}/{name}"
        if proto == "webrtc":
            # MediaMTX serves a WHEP/WebRTC page/endpoint at this path.
            return f"http://{self._host}:{_WEBRTC_PORT}/{name}"
        if proto == "hls":
            # HLS playlist entrypoint.
            return f"http://{self._host}:{_HLS_PORT}/{name}/index.m3u8"
        raise ValueError(f"unsupported proto {proto!r}; use rtsp | webrtc | hls")

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        """Close the underlying HTTP connection pool."""
        self._client.close()

    def __enter__(self) -> "MediaMTXClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
