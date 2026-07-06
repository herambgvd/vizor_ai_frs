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
import os
import threading
import time

from edge.core.logging import get_logger
from edge.db.base import get_sessionmaker

log = get_logger("frs.supervisor")

# Don't re-emit an event for the same (camera, identity) within this window.
COOLDOWN_SECONDS = 15.0
# How often the supervisor re-reads the camera table to pick up add/edit/disable.
REFRESH_SECONDS = 20.0


def _envf(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _envi(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Staged-pipeline tunables — env-based FALLBACK DEFAULTS ONLY. The live values are
# read from FrsSettings at worker start (see CameraWorker.__init__); these apply only
# when the settings row can't be loaded. Defaults mirror vizor_nvr
# scenarios/frs/config/settings.py. Do NOT lower them: looser gates admit
# tiny/angled/blurry faces that pollute the vote consensus.
LIVE_DET_CONF = _envf("FRS_LIVE_DET_CONF", 0.5)               # SCRFD detect threshold
LIVE_MIN_FACE_PX = _envi("FRS_LIVE_MIN_FACE_PX", 80)          # min bbox side (px)
LIVE_MIN_SHARPNESS = _envf("FRS_LIVE_MIN_SHARPNESS", 60.0)    # Laplacian variance
LIVE_MAX_POSE_DEG = _envf("FRS_LIVE_MAX_POSE_DEG", 40.0)      # max |yaw|/|pitch|/|roll|
# Higher bar to EMIT an "Unknown" than to detect, so SCRFD false positives
# (back-of-head / hand / blur) are tracked+voted but never surfaced as noise.
LIVE_UNKNOWN_MIN_DET_CONF = _envf("FRS_LIVE_UNKNOWN_MIN_DET_CONF", 0.65)
# Multi-frame consensus before an identity is emitted (vizor_nvr default = 5).
LIVE_VOTE_MIN_FRAMES = _envi("FRS_LIVE_VOTE_MIN_FRAMES", 5)
# Once a track is firmly recognised (score >= this) stop re-evaluating it.
LIVE_HIGH_CONF_SCORE = _envf("FRS_LIVE_HIGH_CONF_SCORE", 0.75)
# Skip recognition on a frame where the face moved > this fraction of its bbox side
# (likely motion-blurred); the track stays alive so sharp frames still vote.
LIVE_MOTION_BLUR_MAX_DISP_RATIO = _envf("FRS_LIVE_MOTION_BLUR_MAX_DISP_RATIO", 0.35)
# Default gallery-match cosine when a camera doesn't set min_confidence.
SIMILARITY_THRESHOLD = _envf("FRS_SIMILARITY", 0.6)


def _normalize_roi(raw):
    """Normalise a camera ROI to a list-of-polygons of [[x,y],...] in 0..1 coords.
    Accepts [[x,y],...] (single flat polygon), [{"points":[...]}], or a list of
    polygons. Returns None when empty → the whole frame is processed. Mirrors
    vizor_nvr live/worker.CameraWorker.roi."""
    if not raw:
        return None
    if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)) and len(raw[0]) == 2:
        return [raw]  # single flat polygon → wrap as one polygon
    return raw


def _point_in_any_roi(px: float, py: float, polygons) -> bool:
    """Ray-cast point-in-polygon over normalised [[x,y],...] polygons."""
    for poly in polygons or []:
        pts = poly.get("points") if isinstance(poly, dict) else poly
        if not pts or len(pts) < 3:
            continue
        inside = False
        n = len(pts)
        j = n - 1
        for i in range(n):
            xi, yi = pts[i][0], pts[i][1]
            xj, yj = pts[j][0], pts[j][1]
            if (yi > py) != (yj > py):
                xint = (xj - xi) * (py - yi) / (yj - yi + 1e-12) + xi
                if px < xint:
                    inside = not inside
            j = i
        if inside:
            return True
    return False


class CameraWorker(threading.Thread):
    """Pulls frames from one camera and submits recognised sightings."""

    def __init__(self, camera, loop: asyncio.AbstractEventLoop):
        super().__init__(daemon=True, name=f"cam-{camera.id}")
        self.camera = camera
        self.loop = loop
        self._stop = threading.Event()
        self._cooldown: dict[str, float] = {}
        self._cam_key = str(camera.id)
        # All recognition params are PER-CAMERA (vizor_nvr camera_config_schema
        # parity), read straight off the camera object. The env-based module
        # constants are only a fallback default when a field is unset. Editing any
        # of these restarts the worker so the new values take effect (see _cfg_sig).
        def _val(attr, default):
            v = getattr(camera, attr, None)
            return v if v is not None else default

        self._min_conf = float(_val("min_confidence", SIMILARITY_THRESHOLD))
        self._live_det_conf = float(_val("det_conf", LIVE_DET_CONF))
        self._min_face_px = int(_val("min_face_px", LIVE_MIN_FACE_PX))
        self._live_min_sharpness = float(_val("min_sharpness", LIVE_MIN_SHARPNESS))
        self._live_max_pose_deg = float(_val("max_pose_deg", LIVE_MAX_POSE_DEG))
        self._vote_min_frames = int(_val("dwell_min_frames", LIVE_VOTE_MIN_FRAMES))
        self._cooldown_seconds = float(_val("alert_suppress_seconds", COOLDOWN_SECONDS))
        self._live_fps = int(_val("fps", 10))
        self._liveness_enabled = bool(_val("liveness_enabled", True))
        self._liveness_threshold = float(_val("liveness_threshold", 0.7))
        self._detection_only = bool(_val("detection_enabled", False))
        # Kept GLOBAL env constants — NOT in the per-camera schema (vizor_nvr keeps
        # these global too).
        self._live_unknown_min_det_conf = LIVE_UNKNOWN_MIN_DET_CONF
        self._high_conf_score = LIVE_HIGH_CONF_SCORE
        self._motion_blur_ratio = LIVE_MOTION_BLUR_MAX_DISP_RATIO
        # Region(s) of interest (normalised polygons); None → whole frame.
        self._roi = _normalize_roi(getattr(camera, "roi", None))
        # Stateful staged pipeline (built lazily on first frame so a missing
        # recognition package never breaks worker construction).
        self._tracker = None
        self._votes = None
        self._prev_centroid: dict[int, tuple[float, float, float]] = {}
        self._last_gc = 0.0
        # Wall-clock of the last decoded frame — the supervisor watches this to flip a
        # camera to "offline" when the stream stalls (no frames) and back to "online".
        self.last_frame_at = time.time()

    def _ensure_pipeline(self) -> bool:
        """Build the per-camera ByteTracker + TrackVoteBuffer once. Returns False if
        the recognition package can't be imported (worker then idles harmlessly)."""
        if self._tracker is not None and self._votes is not None:
            return True
        try:
            from .recognition.tracker import ByteTracker
            from .recognition.voting import TrackVoteBuffer

            self._tracker = ByteTracker(iou_threshold=0.08, max_age=120,
                                        high_thresh=0.4, low_thresh=0.1)
            self._votes = TrackVoteBuffer(min_frames=self._vote_min_frames)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("pipeline init failed cam=%s err=%s", self.camera.id, exc)
            return False

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        import cv2

        from edge.stream.rtsp import RTSPReader

        c = self.camera
        log.info("camera worker start id=%s name=%s fps=%s", c.id, c.name, c.fps)
        reader = RTSPReader(
            c.rtsp_url,
            fps=max(1, int(c.fps or self._live_fps)),
            reconnect=True,
            hw_accel=getattr(c, "hw_accel", "none") or "none",
            max_width=int(getattr(c, "analyze_width", 0) or 0),
        )
        got_frame = False
        try:
            for frame in reader.frames():
                if self._stop.is_set():
                    break
                self.last_frame_at = time.time()   # liveness heartbeat for the supervisor
                if not got_frame:  # first decoded frame => camera is confirmed online
                    got_frame = True
                    self._set_status("online")
                try:
                    # Stateful staged pipeline: detect → track → quality/pose/sharpness
                    # gate → align → embed → match → multi-frame vote consensus. Only
                    # faces that clear consensus + the cooldown are returned to persist.
                    faces = self._process_frame(frame)
                except Exception as exc:  # noqa: BLE001 — never let one bad frame kill the worker
                    log.warning("recognise failed cam=%s err=%s", c.id, exc)
                    continue
                # Snapshot = the FULL frame (scene context), encoded ONCE per frame and
                # shared by every face in it — the operator sees where the person is,
                # not a redundant face crop. Kept at native resolution so the stored
                # (native-pixel) bbox maps 1:1 onto it for the client-side detected-face
                # crop + box overlay. JPEG q85 bounds the size.
                snapshot = None
                if faces:
                    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    snapshot = buf.tobytes() if ok else None
                for f in faces:
                    asyncio.run_coroutine_threadsafe(self._persist(f, snapshot), self.loop)
        except Exception as exc:  # noqa: BLE001
            log.warning("camera worker error id=%s err=%s", c.id, exc)
            self._set_status("error", str(exc)[:500])
        finally:
            reader.close()
            log.info("camera worker stop id=%s", c.id)

    def _process_frame(self, frame) -> list:
        """One frame through the tracked+voted recognition pipeline (mirrors
        vizor_nvr live/worker.CameraWorker._process_frame). Returns a list of
        ``live.LiveFace`` verdicts that passed consensus, the fire state-machine,
        and the per-identity cooldown — ready to persist as events."""
        import numpy as np

        from . import gallery
        from .live import LiveFace
        from .recognition import get_engine
        from .recognition.align import _landmarks_sane
        from .recognition.quality import (
            crop_face,
            crop_face_with_margin,
            estimate_pose_from_landmarks,
            face_sharpness,
            is_face_usable,
        )
        from .recognition.tracker import assign_track_ids

        eng = get_engine()
        if not eng.available or not self._ensure_pipeline():
            return []

        cam = self._cam_key
        now = time.time()
        if now - self._last_gc > 5.0:
            self._votes.gc(now)
            cutoff = now - 300.0
            self._prev_centroid = {k: v for k, v in self._prev_centroid.items() if v[2] > cutoff}
            self._last_gc = now

        h, w = frame.shape[:2]
        try:
            dets = eng.detect(frame, conf_thresh=self._live_det_conf)
        except Exception:  # noqa: BLE001
            return []

        # ── per-face quality gate + align + embed + match ──────────────────
        prepped: list[dict] = []
        for d in dets:
            bbox = np.asarray(d.bbox, dtype=np.float32)
            # ROI gate — drop a face whose centre is outside the camera's region(s)
            # of interest (normalised polygons). Empty ROI → whole frame.
            if self._roi is not None:
                cx = (bbox[0] + bbox[2]) / 2.0 / max(w, 1)
                cy = (bbox[1] + bbox[3]) / 2.0 / max(h, 1)
                if not _point_in_any_roi(cx, cy, self._roi):
                    continue
            ok, _reason = is_face_usable(bbox, w, h, min_face_px=self._min_face_px)
            if not ok:
                continue
            if face_sharpness(crop_face(frame, bbox, w, h)) < self._live_min_sharpness:
                continue
            lms = np.asarray(d.kps, dtype=np.float32) if d.kps is not None else None
            # Sane 5-point face geometry. Real faces have it; SCRFD false positives on
            # non-faces (shoes, boxes) collapse the landmarks. Used to pose-gate AND to
            # suppress bogus "Unknown" events below.
            lms_sane = lms is not None and float(lms.sum()) != 0.0 and _landmarks_sane(lms, bbox)
            if lms_sane:
                yaw, pitch, roll = estimate_pose_from_landmarks(lms)
                if max(abs(yaw), abs(pitch), abs(roll)) > self._live_max_pose_deg:
                    continue
            vec = eng.embed_face(frame, d, denoise=True)
            if vec is None:
                continue
            # Best gallery hit at/above the camera threshold → the person vote.
            pid = pname = None
            mscore = 0.0
            for hit in gallery.search(vec, limit=10):
                s = float(hit.get("score", 0.0))
                if s >= self._min_conf and hit.get("person_id") and s > mscore:
                    pid, pname, mscore = str(hit["person_id"]), hit.get("person_name"), s
            prepped.append({"bbox": bbox, "conf": float(d.score), "vec": vec, "det": d,
                            "pid": pid, "pname": pname, "mscore": mscore, "lms_sane": lms_sane})

        if not prepped:
            return []

        # ── track → vote → consensus → fire state-machine ─────────────────
        track_ids = assign_track_ids(self._tracker, [(p["bbox"], p["conf"]) for p in prepped])
        out: list = []
        for i, p in enumerate(prepped):
            tid = track_ids[i] if i < len(track_ids) else 0
            bbox = p["bbox"]

            # High-confidence lock: a firmly recognised track is not re-evaluated.
            tstate = self._votes.state(cam, tid)
            if tstate is not None and tstate.get("status") == "recognized" \
                    and float(tstate.get("score", 0.0)) >= self._high_conf_score:
                self._votes.touch_state(cam, tid, now)
                continue

            # Motion-blur gate: skip a frame where the centroid jumped a large
            # fraction of the bbox side; the track stays alive so sharp frames vote.
            cx = (bbox[0] + bbox[2]) / 2.0
            cy = (bbox[1] + bbox[3]) / 2.0
            bb_side = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
            prev = self._prev_centroid.get(tid)
            self._prev_centroid[tid] = (cx, cy, now)
            if prev is not None and bb_side > 1.0:
                disp = ((cx - prev[0]) ** 2 + (cy - prev[1]) ** 2) ** 0.5
                if disp / bb_side > self._motion_blur_ratio:
                    continue

            self._votes.record(cam, tid, p["pid"], p["mscore"], p["vec"], p["pname"], now)
            if not self._votes.should_fire(cam, tid, now, min_frames=self._vote_min_frames):
                continue
            consensus = self._votes.consensus(cam, tid)
            self._votes.clear(cam, tid)
            if consensus is None:
                continue
            cpid, cscore, _emb, cname = consensus
            if self._detection_only:
                # Detection-only camera: report a face was present, don't identify it.
                event_type = "face_detected"
                cpid = cname = None
                cscore = 0.0
            else:
                event_type = "face_recognized" if cpid else "face_unknown"

            # False-positive gate for non-identified events (UNKNOWN / DETECTED): require a higher detection
            # confidence AND sane face landmarks to emit an unknown. SCRFD sometimes
            # fires confidently on non-faces (shoes, boxes) that never match the
            # gallery — those have degenerate landmarks and would otherwise spam
            # "Unknown". Recognised faces matched the gallery, so they're exempt.
            if not cpid and (p["conf"] < self._live_unknown_min_det_conf or not p.get("lms_sane")):
                continue

            prior_status = tstate.get("status") if tstate else None
            prior_score = float(tstate.get("score", 0.0)) if tstate else 0.0
            prior_pid = tstate.get("person_id") if tstate else None
            should_fire = (
                prior_status is None
                or (prior_status == "unknown" and event_type == "face_recognized")
                or (event_type == "face_recognized" and cpid != prior_pid)
                or (prior_status == "recognized" and prior_score < self._high_conf_score
                    and cscore >= prior_score + 0.05)
            )
            self._votes.set_state(cam, tid, "recognized" if cpid else "unknown",
                                  cpid, cname, cscore, now)
            if not should_fire:
                continue

            # Cooldown so a lingering face doesn't spam events. Keyed by identity when
            # recognised, else per-track (so distinct unknown/detected people each get
            # an event rather than one global anonymous cooldown).
            key = cpid or f"__anon__{tid}"
            if now - self._cooldown.get(key, 0) < self._cooldown_seconds:
                continue
            self._cooldown[key] = now

            x1, y1, x2, y2 = (int(v) for v in bbox)
            crop = crop_face_with_margin(frame, bbox, w, h)
            lf = LiveFace(
                event_type, [x1, y1, x2, y2],
                round(float(cscore), 4) if cpid else None,
                cpid, cname, None, crop,
                # Carry the already-computed embedding so record_event indexes it
                # straight into the forensic snapshots collection (re-detecting a
                # face in the tight crop fails → Investigate would find nothing).
                _emb if _emb is not None else p["vec"],
            )
            # Liveness / anti-spoof gate. When enabled on the camera, score the crop;
            # a live-probability below the camera threshold flags a presentation attack
            # (printed photo / phone screen) → emit spoof_detected instead of the
            # recognition, and drop the identity (a spoof isn't a real sighting).
            if self._liveness_enabled:
                try:
                    live_p = eng.liveness(frame, p["det"])
                except Exception:  # noqa: BLE001
                    live_p = None
                if live_p is not None:
                    lf.liveness_score = round(float(live_p), 4)
                    if live_p < self._liveness_threshold:
                        lf.event_type = "spoof_detected"
                        lf.person_id = lf.person_name = None
                        lf.confidence = None
            # Demographics (age/gender via FairFace) — computed once here, only on an
            # emitted event (post-consensus), not every frame, to bound GPU cost.
            try:
                demo = eng.age_gender(frame, p["det"])
            except Exception:  # noqa: BLE001
                demo = None
            if demo:
                a = demo.get("age")
                lf.age = str(a) if a is not None else None
                lf.age_range = demo.get("age_range")
                lf.gender = demo.get("gender")
                lf.gender_confidence = demo.get("gender_confidence")
            out.append(lf)
        return out

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
                    direction=getattr(c, "direction", None) or "both",
                    embedding=getattr(f, "embedding", None),
                    age=getattr(f, "age", None),
                    age_range=getattr(f, "age_range", None),
                    gender=getattr(f, "gender", None),
                    gender_confidence=getattr(f, "gender_confidence", None),
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


def _cfg_sig(cam) -> str:
    """Order-stable signature of the recognition-affecting PER-CAMERA config.
    Editing a camera's name/location does NOT change it (no needless worker churn),
    but any recognition param / rtsp_url / hw_accel / direction / ROI does → the
    supervisor restarts the worker so the new params take effect. Mirrors vizor_nvr
    live/manager._cfg_sig."""
    import json

    return json.dumps(
        {
            "rtsp_url": getattr(cam, "rtsp_url", None),
            "fps": getattr(cam, "fps", None),
            "min_confidence": getattr(cam, "min_confidence", None),
            "detection_enabled": getattr(cam, "detection_enabled", None),
            "direction": getattr(cam, "direction", None),
            "liveness_enabled": getattr(cam, "liveness_enabled", None),
            "liveness_threshold": getattr(cam, "liveness_threshold", None),
            "det_conf": getattr(cam, "det_conf", None),
            "min_face_px": getattr(cam, "min_face_px", None),
            "min_sharpness": getattr(cam, "min_sharpness", None),
            "max_pose_deg": getattr(cam, "max_pose_deg", None),
            "dwell_min_frames": getattr(cam, "dwell_min_frames", None),
            "alert_suppress_seconds": getattr(cam, "alert_suppress_seconds", None),
            "hw_accel": getattr(cam, "hw_accel", None),
            "analyze_width": getattr(cam, "analyze_width", None),
            "roi": getattr(cam, "roi", None),
        },
        sort_keys=True,
        default=str,
    )


async def _load_cameras():
    """Snapshot of cameras with the scenario turned ON (detached simple objects)."""
    from sqlalchemy import select

    from .domain.models import Camera

    async with get_sessionmaker()() as db:
        rows = (
            await db.execute(
                select(Camera).where(Camera.enabled.is_(True), Camera.recognition_enabled.is_(True))
            )
        ).scalars().all()
        # Detach lightweight copies (with ALL per-camera recognition params) so
        # worker threads never touch the async session.
        return [
            type("Cam", (), {
                "id": c.id, "name": c.name, "rtsp_url": c.rtsp_url, "fps": c.fps,
                "min_confidence": c.min_confidence, "detection_enabled": c.detection_enabled,
                "direction": c.direction, "liveness_enabled": c.liveness_enabled,
                "liveness_threshold": c.liveness_threshold, "det_conf": c.det_conf,
                "min_face_px": c.min_face_px, "min_sharpness": c.min_sharpness,
                "max_pose_deg": c.max_pose_deg, "dwell_min_frames": c.dwell_min_frames,
                "alert_suppress_seconds": c.alert_suppress_seconds, "hw_accel": c.hw_accel,
                "analyze_width": c.analyze_width,
                "roi": c.roi,
            })()
            for c in rows
        ]


async def _mark_status(cam_id, cam_name: str, status: str) -> None:
    """Persist a camera's online/offline state and raise an in-app notification
    (bell) for every active operator on the transition."""
    from sqlalchemy import select

    from .domain.models import Camera

    async with get_sessionmaker()() as db:
        cam = await db.get(Camera, cam_id)
        if cam is not None:
            cam.status = status
            cam.last_error = "stream unreachable" if status == "offline" else None
            await db.commit()
        try:
            from edge.auth.models import User
            from edge.messaging.dispatcher import notify

            uids = (await db.execute(select(User.id).where(User.is_active.is_(True)))).scalars().all()
            if uids:
                offline = status == "offline"
                await notify(
                    db, user_ids=list(uids),
                    title=f"Camera {'offline' if offline else 'back online'}",
                    body=f"{cam_name} {'is offline — no video stream received.' if offline else 'is online again.'}",
                )
        except Exception as exc:  # noqa: BLE001 — never let a notify failure break the loop
            log.warning("camera-status notify failed cam=%s: %s", cam_id, exc)


async def supervise() -> None:
    """Reconcile running workers with the enabled-camera set forever."""
    loop = asyncio.get_running_loop()
    workers: dict[str, CameraWorker] = {}
    sigs: dict[str, str] = {}
    offline_state: dict[str, bool] = {}   # cid -> currently flagged offline
    offline_after = _envf("FRS_OFFLINE_SECONDS", 45.0)
    log.info("FRS stream supervisor started")
    while True:
        try:
            cams = await _load_cameras()
        except Exception as exc:  # noqa: BLE001
            log.warning("camera load failed: %s", exc)
            cams = []
        want = {str(c.id): c for c in cams}

        # Stop a worker whose camera was removed / scenario turned off, that died,
        # OR whose per-camera recognition config changed — restart to pick up new
        # params / ROI / thresholds.
        for cid in list(workers):
            changed = cid in want and _cfg_sig(want[cid]) != sigs.get(cid)
            if cid not in want or not workers[cid].is_alive() or changed:
                workers[cid].stop()
                workers.pop(cid, None)
                sigs.pop(cid, None)
                if changed:
                    log.info("camera %s config changed → restarting worker", cid)
        # Start a worker for every desired camera not currently running (new,
        # newly scenario-on, or just stopped for a config-change restart).
        for cid, cam in want.items():
            if cid not in workers:
                w = CameraWorker(cam, loop)
                w.start()
                workers[cid] = w
                sigs[cid] = _cfg_sig(cam)

        # ── Offline watchdog: no decoded frame for `offline_after`s → flip the camera
        # to "offline" (+ notify once); frames resuming flips it back to "online". ──
        now = time.time()
        for cid, w in list(workers.items()):
            stale = (now - getattr(w, "last_frame_at", now)) > offline_after
            if stale and not offline_state.get(cid):
                offline_state[cid] = True
                await _mark_status(w.camera.id, getattr(w.camera, "name", "Camera"), "offline")
            elif not stale and offline_state.get(cid):
                offline_state[cid] = False
                await _mark_status(w.camera.id, getattr(w.camera, "name", "Camera"), "online")
        for cid in list(offline_state):        # forget workers that were removed
            if cid not in workers:
                offline_state.pop(cid, None)

        if not workers:
            log.info("no cameras with the scenario on; idling")
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
