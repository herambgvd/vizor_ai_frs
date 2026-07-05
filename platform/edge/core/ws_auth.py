"""WebSocket authentication/authorization helpers.

HTTP dependencies (``Depends(require_permission(...))``) do NOT run on a WebSocket
handshake — Starlette only invokes the endpoint coroutine, so a WS route is OPEN
unless it authenticates itself. These two helpers close that gap by validating the
same HS256 access token the REST API uses, reusing ``decode_token`` and the ``User``
role model so a WS connection enforces the exact same RBAC as an HTTP request.

HOW THE FRONTEND PASSES THE TOKEN
---------------------------------
The browser ``WebSocket`` constructor cannot set an ``Authorization`` header, so the
canonical transport is a QUERY-STRING param:

    const ws = new WebSocket(`ws://host/api/system/resources/stream?token=${accessToken}`)

We therefore read ``?token=<access>`` first. As fallbacks (native clients, proxies)
we also accept an ``Authorization: Bearer <access>`` header and the
``Sec-WebSocket-Protocol`` subprotocol (some clients smuggle the token there when a
query string is undesirable). The access token is the SHORT-lived one — never the
refresh token — so a leaked WS URL expires quickly.

Close codes (application range 4000-4999):
  * 4401 — unauthenticated (missing/invalid/expired token, or inactive/unknown user).
  * 4403 — authenticated but the role lacks the required permission.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import WebSocket

from ..auth.security import decode_token
from ..db.base import get_sessionmaker
from .logging import get_logger

log = get_logger("edge.ws_auth")


def _extract_token(websocket: WebSocket) -> str | None:
    """Pull the access token off the handshake: ?token= first, then Authorization
    header (Bearer), then the Sec-WebSocket-Protocol subprotocol. Returns None if
    no token is present anywhere."""
    # 1) Query string — the browser-friendly path (WebSocket can't set headers).
    token = websocket.query_params.get("token")
    if token:
        return token
    # 2) Authorization header — "Bearer <token>" (native clients / proxies).
    auth = websocket.headers.get("authorization")
    if auth and auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    # 3) Subprotocol — some clients pass the token as the requested subprotocol.
    proto = websocket.headers.get("sec-websocket-protocol")
    if proto:
        # A comma-separated list; take the first non-empty entry as the token.
        first = proto.split(",")[0].strip()
        return first or None
    return None


async def authenticate_ws(websocket: WebSocket):
    """Authenticate a WebSocket from its access token.

    Returns the live ``User`` on success. On any failure (no token, bad signature /
    expiry, wrong token type, unknown or inactive user) it closes the socket with
    code 4401 and returns None — the caller must ``return`` immediately when None.
    """
    # Imported lazily to avoid an import cycle (auth.models -> db.base -> ... -> core).
    from ..auth.models import User

    token = _extract_token(websocket)
    if not token:
        log.debug("ws auth: no token on handshake")
        await websocket.close(code=4401)
        return None

    try:
        claims = decode_token(token)  # verifies HS256 signature + expiry
    except jwt.PyJWTError:
        log.debug("ws auth: token decode failed")
        await websocket.close(code=4401)
        return None

    # Only ACCESS tokens grant access; a refresh token must never open a socket.
    if claims.get("type") != "access":
        log.debug("ws auth: non-access token type=%s", claims.get("type"))
        await websocket.close(code=4401)
        return None

    sub = claims.get("sub")
    try:
        user_id = uuid.UUID(str(sub))
    except (ValueError, TypeError):
        log.debug("ws auth: malformed sub claim")
        await websocket.close(code=4401)
        return None

    # Load the user fresh so a deactivation takes effect immediately (like HTTP).
    async with get_sessionmaker()() as db:
        user = await db.get(User, user_id)

    if user is None or not user.is_active:
        log.debug("ws auth: user missing or inactive")
        await websocket.close(code=4401)
        return None

    return user


async def authorize_ws(websocket: WebSocket, permission: str):
    """Authenticate, then require the user's role to grant ``permission``.

    Returns the ``User`` on success. Closes with 4401 if unauthenticated (delegated
    to ``authenticate_ws``) or 4403 if authenticated but not permitted, returning
    None in either case — the caller must ``return`` on None.
    """
    user = await authenticate_ws(websocket)
    if user is None:
        # authenticate_ws already closed with 4401.
        return None
    if not user.role.grants(permission):
        log.debug("ws auth: user %s lacks permission %s", user.id, permission)
        await websocket.close(code=4403)
        return None
    return user
