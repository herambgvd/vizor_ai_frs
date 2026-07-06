"""FRS live feed — most-recent recognitions for the monitoring wall.

Matches vizor_nvr's polling model: the Live page polls this every few seconds
for the newest sightings (the recognition worker writes them; see
:mod:`app.stream_supervisor`). Thin projection over ``frs_events`` scoped to a
short recency window so the feed stays snappy. Gated by ``frs.event.read``.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import uuid

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from edge.auth.deps import require_permission
from edge.auth.security import decode_token
from edge.core.errors import ForbiddenError, NotFoundError, UnauthorizedError
from edge.core.logging import get_logger
from edge.core.storage import get_storage
from edge.db.base import get_db, get_sessionmaker
from edge.stream.mediamtx import MediaMTXClient, MediaMTXError

from .. import events as events_bus
from ..domain.models import Camera, FRSEvent
from ..domain.permissions import FrsPerm

log = get_logger("frs.live")

router = APIRouter(prefix="/frs/live", tags=["frs-live"])

# Keepalive comment cadence for the SSE stream (seconds). Long enough to be quiet,
# short enough that proxies (nginx/Caddy) never drop an "idle" connection.
_SSE_KEEPALIVE_S = 15


async def _authenticate_token(token: str):
    """Authenticate an SSE caller from a ``?token=<access>`` query param.

    EventSource / <img> cannot set an Authorization header, so the browser passes the
    same short-lived access token used by the REST API as a query param (mirrors the
    WebSocket token transport in edge.core.ws_auth). Enforces the same
    ``frs.event.read`` permission as the polling feed. Raises on any failure.
    """
    from edge.auth.models import User

    if not token:
        raise UnauthorizedError("missing token")
    try:
        payload = decode_token(token)  # verifies HS256 signature + expiry
    except jwt.PyJWTError:
        raise UnauthorizedError("invalid or expired token")
    if payload.get("type") != "access":
        raise UnauthorizedError("not an access token")
    try:
        user_id = uuid.UUID(str(payload.get("sub")))
    except (TypeError, ValueError):
        raise UnauthorizedError("malformed token")
    async with get_sessionmaker()() as db:  # short-lived — not held during streaming
        user = await db.get(User, user_id)  # role selectin-loaded
        if user is None or not user.is_active:
            raise UnauthorizedError("user not found or inactive")
        if not user.role.grants(FrsPerm.EVENT_READ):
            raise ForbiddenError(f"missing permission: {FrsPerm.EVENT_READ}")
    return user


@router.get("/stream")
async def live_stream(request: Request, token: str = Query(...)) -> StreamingResponse:
    """Realtime SSE feed of new FRS recognition events for the authenticated Live wall.

    Subscribes to the in-process event bus and pushes each recorded sighting as an SSE
    ``data:`` frame (``{id, event_type, camera_id, camera_name, person_id, person_name,
    authorized, auth_reason, group_name, snapshot_url, triggered_at}``). Emits a
    ``: keepalive`` comment every ~15s so proxies keep the connection open, and
    unsubscribes on client disconnect. Auth: ``?token=<access>`` (see
    ``_authenticate_token``). Complements — does not replace — the polling
    ``GET /frs/live`` feed.
    """
    await _authenticate_token(token)
    q = events_bus.subscribe()

    async def _gen():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=_SSE_KEEPALIVE_S)
                    yield f"data: {json.dumps(item)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            events_bus.unsubscribe(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.get("")
async def live_feed(
    camera_id: uuid.UUID | None = None,
    limit: int = Query(30, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Newest recognitions (last 10 minutes), optionally scoped to a camera."""
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
    stmt = select(FRSEvent).where(FRSEvent.triggered_at >= since)
    if camera_id:
        stmt = stmt.where(FRSEvent.camera_id == camera_id)
    rows = (await db.execute(stmt.order_by(FRSEvent.triggered_at.desc()).limit(limit))).scalars().all()
    storage = get_storage()
    items = []
    for e in rows:
        attrs = e.attributes or {}
        items.append({
            "id": str(e.id),
            "event_type": e.event_type,
            "person_id": str(e.person_id) if e.person_id else None,
            "person_name": e.person_name,
            "camera_id": str(e.camera_id) if e.camera_id else None,
            "camera_name": e.camera_name,
            "confidence": e.confidence,
            "liveness_score": e.liveness_score,
            "snapshot_url": await storage.url(e.snapshot_key) if e.snapshot_key else None,
            "triggered_at": e.triggered_at.isoformat() if e.triggered_at else None,
            # Extra fields so the Live events modal can show complete info.
            "title": e.title,
            "severity": e.severity,
            "detection_type": e.detection_type,
            "track_id": e.track_id,
            "bbox": e.bbox or [],
            "age": e.age,
            "age_range": e.age_range,
            "gender": e.gender,
            "gender_confidence": e.gender_confidence,
            "authorized": attrs.get("authorized"),
            "auth_reason": attrs.get("auth_reason"),
            "group_name": attrs.get("group_name"),
            "direction": attrs.get("direction"),
        })
    return {"items": items}


# =============================================================================
# Live video streams — register a camera's RTSP under MediaMTX and hand the
# browser back HLS / WebRTC republish URLs for the VMS wall. MediaMTX pulls the
# camera on demand and re-publishes it on host-published ports (browser-reachable
# via ``mediamtx_public_host``), so the Live wall never touches the camera RTSP.
# =============================================================================

def _stream_urls_for(camera: Camera) -> dict:
    """Ensure a MediaMTX path for ``camera`` and return its playback URLs.

    Registers (idempotently — ``add_path`` replaces) a path ``cam-<id>`` that
    pulls the camera RTSP, then derives browser-reachable HLS + WebRTC URLs.
    Raises :class:`MediaMTXError` on any control-plane failure (caller maps it
    to a 502).
    """
    name = f"cam-{camera.id}"
    client = MediaMTXClient()
    try:
        try:
            client.add_path(name, camera.rtsp_url)
        except MediaMTXError as exc:
            # add_path isn't idempotent — MediaMTX 400s if the path is already
            # registered. That's the happy path for a re-mount: the stream is live,
            # so treat "already exists" as success and just hand back the URLs.
            if "already exists" not in str(exc):
                raise
            log.debug("MediaMTX path %s already registered — reusing", name)
        return {
            "name": name,
            "hls": client.read_url(name, "hls"),
            "webrtc": client.read_url(name, "webrtc"),
        }
    finally:
        client.close()


@router.post("/streams/{camera_id}")
async def register_stream(
    camera_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Register (or refresh) the live MediaMTX stream for one camera and return its URLs.

    Looks up the camera, republishes its RTSP under ``cam-<id>`` in MediaMTX, and
    returns ``{name, hls, webrtc}`` — the HLS playlist the wall's ``hls.js`` player
    loads and the WebRTC/WHEP page. Idempotent (safe to call on every tile mount).
    Returns 404 for an unknown camera, 502 if MediaMTX rejects the path.
    """
    camera = await db.get(Camera, camera_id)
    if camera is None:
        raise NotFoundError(f"camera {camera_id} not found")
    try:
        # _stream_urls_for makes blocking sync HTTP calls to MediaMTX — run it off the
        # event loop so it doesn't stall other requests.
        return await run_in_threadpool(_stream_urls_for, camera)
    except MediaMTXError as exc:
        log.error("MediaMTX register failed for camera %s: %s", camera_id, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/streams")
async def list_streams(
    db: AsyncSession = Depends(get_db),
    _=Depends(require_permission(FrsPerm.EVENT_READ)),
) -> dict:
    """Ensure + return live-stream URLs for every enabled camera (bulk wall bootstrap).

    Registers each enabled camera's MediaMTX path and returns a list of
    ``{camera_id, name, hls, webrtc}``. A camera whose registration fails is
    reported with ``error`` set instead of URLs, so one bad RTSP never fails the
    whole wall.
    """
    rows = (
        await db.execute(select(Camera).where(Camera.enabled.is_(True)).order_by(Camera.name))
    ).scalars().all()
    items = []
    for c in rows:
        entry = {"camera_id": str(c.id)}
        try:
            # Blocking sync MediaMTX HTTP calls — keep them off the event loop.
            entry.update(await run_in_threadpool(_stream_urls_for, c))
        except MediaMTXError as exc:
            entry["error"] = str(exc)
            log.warning("MediaMTX register failed for camera %s: %s", c.id, exc)
        items.append(entry)
    return {"items": items}
