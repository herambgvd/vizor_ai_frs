"""Live FRS stream supervisor — the recognition worker process.

Runs OUTSIDE the API process (its own container/`python -m app.stream_supervisor`,
behind the compose ``live`` profile). For every enabled camera with recognition
on, a worker thread pulls frames via the shared FFmpeg RTSPReader, recognises
faces with :mod:`app.live`, and persists sightings via the shared
:func:`app.events.record_event` — the same writer the ingest API uses, so live
events flow into Events / Investigate / Counting / Attendance automatically.

Recognition is CPU/ONNX by default; set a camera's ``hw_accel=nvdec`` to decode on
the GPU. A per-(camera, person) cooldown prevents event spam from a lingering face.

This module is import-safe on a machine with no cameras: it simply finds no
enabled cameras and idles, refreshing the camera list periodically.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import threading
import time

from edge.core.logging import get_logger
from edge.db.base import get_sessionmaker

log = get_logger("frs.supervisor")

# Don't re-emit an event for the same (camera, identity) within this window.
COOLDOWN_SECONDS = 15.0
# How often the supervisor re-reads the camera table to pick up add/edit/disable.
REFRESH_SECONDS = 20.0


class CameraWorker(threading.Thread):
    """Pulls frames from one camera and submits recognised sightings."""

    def __init__(self, camera, loop: asyncio.AbstractEventLoop):
        super().__init__(daemon=True, name=f"cam-{camera.id}")
        self.camera = camera
        self.loop = loop
        self._stop = threading.Event()
        self._cooldown: dict[str, float] = {}

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        import cv2

        from edge.stream.rtsp import RTSPReader

        from . import live

        c = self.camera
        log.info("camera worker start id=%s name=%s fps=%s", c.id, c.name, c.fps)
        reader = RTSPReader(c.rtsp_url, fps=max(1, int(c.fps or 5)), reconnect=True)
        got_frame = False
        try:
            for frame in reader.frames():
                if self._stop.is_set():
                    break
                if not got_frame:  # first decoded frame => camera is confirmed online
                    got_frame = True
                    self._set_status("online")
                try:
                    faces = live.recognize_frame(
                        frame, min_confidence=float(c.min_confidence or 0.45), min_face_px=int(c.min_face_px or 40)
                    )
                except Exception as exc:  # noqa: BLE001 — never let one bad frame kill the worker
                    log.warning("recognise failed cam=%s err=%s", c.id, exc)
                    continue
                for f in faces:
                    key = f.person_id or f"unknown:{f.event_type}"
                    now = time.monotonic()
                    if now - self._cooldown.get(key, 0) < COOLDOWN_SECONDS:
                        continue
                    self._cooldown[key] = now
                    ok, buf = cv2.imencode(".jpg", f.crop_bgr)
                    snapshot = buf.tobytes() if ok else None
                    asyncio.run_coroutine_threadsafe(self._persist(f, snapshot), self.loop)
        except Exception as exc:  # noqa: BLE001
            log.warning("camera worker error id=%s err=%s", c.id, exc)
            self._set_status("error", str(exc)[:500])
        finally:
            reader.close()
            log.info("camera worker stop id=%s", c.id)

    async def _persist(self, f, snapshot: bytes | None) -> None:
        from .events import record_event

        c = self.camera
        async with get_sessionmaker()() as db:
            try:
                await record_event(
                    db,
                    event_type=f.event_type,
                    person_id=f.person_id,
                    person_name=f.person_name,
                    camera_id=c.id,
                    camera_name=c.name,
                    confidence=f.confidence,
                    bbox=f.bbox,
                    snapshot_bytes=snapshot,
                    snapshot_content_type="image/jpeg",
                    liveness_score=f.liveness_score,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("event persist failed cam=%s err=%s", c.id, exc)

    def _set_status(self, status: str, error: str | None = None) -> None:
        asyncio.run_coroutine_threadsafe(self._write_status(status, error), self.loop)

    async def _write_status(self, status: str, error: str | None) -> None:
        from .domain.models import Camera

        async with get_sessionmaker()() as db:
            cam = await db.get(Camera, self.camera.id)
            if cam is not None:
                cam.status = status
                cam.last_error = error
                if status == "online":
                    cam.last_seen_at = dt.datetime.now(dt.timezone.utc)
                await db.commit()


async def _load_cameras():
    """Snapshot of enabled recognition cameras (detached simple objects)."""
    from sqlalchemy import select

    from .domain.models import Camera

    async with get_sessionmaker()() as db:
        rows = (
            await db.execute(
                select(Camera).where(Camera.enabled.is_(True), Camera.recognition_enabled.is_(True))
            )
        ).scalars().all()
        # Detach lightweight copies so worker threads never touch the async session.
        return [
            type("Cam", (), {
                "id": c.id, "name": c.name, "rtsp_url": c.rtsp_url, "fps": c.fps,
                "min_confidence": c.min_confidence, "min_face_px": c.min_face_px, "hw_accel": c.hw_accel,
            })()
            for c in rows
        ]


async def supervise() -> None:
    """Reconcile running workers with the enabled-camera set forever."""
    loop = asyncio.get_running_loop()
    workers: dict[str, CameraWorker] = {}
    log.info("FRS stream supervisor started")
    while True:
        try:
            cams = await _load_cameras()
        except Exception as exc:  # noqa: BLE001
            log.warning("camera load failed: %s", exc)
            cams = []
        want = {str(c.id): c for c in cams}

        # Stop workers whose camera was removed/disabled.
        for cid in list(workers):
            if cid not in want or not workers[cid].is_alive():
                workers[cid].stop()
                workers.pop(cid, None)
        # Start workers for newly-enabled cameras.
        for cid, cam in want.items():
            if cid not in workers:
                w = CameraWorker(cam, loop)
                w.start()
                workers[cid] = w

        if not workers:
            log.info("no enabled recognition cameras; idling")
        await asyncio.sleep(REFRESH_SECONDS)


def main() -> None:
    import logging

    # Standalone process — configure our own logging (no uvicorn to do it for us).
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    try:
        asyncio.run(supervise())
    except KeyboardInterrupt:
        log.info("supervisor interrupted; exiting")


if __name__ == "__main__":
    main()
