"""Realtime WebSocket hub — push live updates to the browser by TOPIC.

Scenarios need to stream events to open UIs: a live video wall, an alert feed, a
resource/health meter, in-app notifications. This provides a tiny pub/sub over
WebSockets: clients connect to ``/api/realtime/{topic}`` and any server code can
``await hub.broadcast(topic, {...})`` to fan a JSON message out to everyone on that
topic.

    # server side, from anywhere (a service, a task callback, an event handler):
    from edge.core.realtime import hub
    await hub.broadcast("alerts", {"type": "motion", "camera": "front-door"})

    # client side:
    const ws = new WebSocket(`ws://host/api/realtime/alerts`)
    ws.onmessage = (e) => render(JSON.parse(e.data))

SCOPE: this hub is single-process, in-memory — connections live in THIS process.
That's perfect for a single app instance. To scale across multiple processes/pods,
back ``broadcast`` with a Redis pub/sub (``settings.redis_url``): publish to a
Redis channel per topic and have each process relay received messages to its local
sockets. Left as a deliberate next step so the common single-node case stays simple.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .logging import get_logger
from .ws_auth import authenticate_ws

log = get_logger("edge.realtime")


class RealtimeHub:
    """In-memory registry of connected WebSockets, grouped by topic.

    ``_topics`` maps a topic name to the set of live sockets subscribed to it.
    A set gives O(1) add/remove and natural de-duplication.
    """

    def __init__(self) -> None:
        self._topics: dict[str, set[WebSocket]] = {}

    async def connect(self, ws: WebSocket, topic: str) -> None:
        """Accept the handshake and register the socket under ``topic``."""
        await ws.accept()
        self._topics.setdefault(topic, set()).add(ws)
        log.debug("ws connect topic=%s (n=%d)", topic, len(self._topics[topic]))

    def disconnect(self, ws: WebSocket, topic: str) -> None:
        """Remove the socket from ``topic``; drop the topic once it's empty."""
        conns = self._topics.get(topic)
        if not conns:
            return
        conns.discard(ws)
        if not conns:
            # No subscribers left — forget the topic so the dict doesn't grow
            # unbounded with stale empty sets.
            self._topics.pop(topic, None)
        log.debug("ws disconnect topic=%s", topic)

    async def broadcast(self, topic: str, message: dict) -> None:
        """Send ``message`` (as JSON) to every socket subscribed to ``topic``.

        Sockets that error on send are assumed dead and pruned, so a broken client
        never blocks or breaks delivery to the others. Iterate over a COPY of the
        set because we mutate it while dropping dead sockets.
        """
        dead: list[WebSocket] = []
        for ws in list(self._topics.get(topic, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 — a dead/closing socket; drop it
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, topic)


# The single shared hub for the whole process.
hub = RealtimeHub()


realtime_router = APIRouter(prefix="/realtime", tags=["realtime"])


@realtime_router.websocket("/{topic}")
async def realtime_ws(ws: WebSocket, topic: str) -> None:
    """WebSocket endpoint: subscribe to ``topic`` and receive its broadcasts.

    This connection is receive-to-detect-disconnect: the server pushes via
    ``hub.broadcast`` while this loop just waits on ``receive_text`` so it notices
    when the client goes away (WebSocketDisconnect) and can clean up its slot.
    Inbound messages from the client are ignored (this hub is server→client push).

    Authenticated: the client passes its access token as ``?token=<access>`` on the
    handshake (see edge.core.ws_auth). ``authenticate_ws`` closes the socket with 4401
    and returns None for a missing/invalid token or an unknown/inactive user — we then
    return before ``hub.connect``, so an unauthenticated client never joins the topic.
    Any authenticated user may subscribe; per-topic authorization can be layered on
    later via ``authorize_ws`` if a topic needs a specific permission.
    """
    user = await authenticate_ws(ws)
    if user is None:
        return  # authenticate_ws already closed the socket (4401)
    await hub.connect(ws, topic)
    try:
        while True:
            # We don't act on client messages; this call parks the coroutine and
            # raises WebSocketDisconnect the moment the socket closes.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.disconnect(ws, topic)
