"""Live face recognition over a single video frame.

Pure CPU/ONNX work (no DB, no I/O) so it is unit-testable and reusable: detect
faces with the shared FaceEngine, embed each, search the enrolled gallery, and
return a match verdict per face. The stream supervisor turns these verdicts into
persisted events; the recognition itself lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from edge.core.config import get_settings
from edge.core.logging import get_logger
from edge.models import get_face_engine

from . import gallery

log = get_logger("frs.live")

# A gallery hit at or above this cosine is accepted as the person (unless the
# camera sets a stricter min_confidence). Below it, the face is "unknown".
RECOGNIZE_COSINE = 0.45


@dataclass
class LiveFace:
    event_type: str            # face_recognized | face_unknown | spoof_detected
    bbox: list                 # [x1, y1, x2, y2]
    confidence: float | None   # match cosine (recognised) else None
    person_id: str | None
    person_name: str | None
    liveness_score: float | None
    crop_bgr: object           # np.ndarray face crop (BGR) for the snapshot


def recognize_frame(bgr, *, min_confidence: float = 0.45, min_face_px: int = 40) -> list[LiveFace]:
    """Detect + recognise every face in a BGR frame. Returns one LiveFace each."""
    eng = get_face_engine()
    if not eng.available:
        return []
    settings = get_settings()
    threshold = max(float(min_confidence), RECOGNIZE_COSINE)

    out: list[LiveFace] = []
    for face in eng.detect(bgr):
        x1, y1, x2, y2 = (int(v) for v in face.bbox)
        if (x2 - x1) < min_face_px or (y2 - y1) < min_face_px:
            continue
        crop = bgr[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]

        # Anti-spoof gate (if enabled): a spoof short-circuits recognition.
        liveness = eng.liveness(bgr, face)
        if settings.pad_enabled and liveness is not None and liveness < settings.pad_threshold:
            out.append(LiveFace("spoof_detected", [x1, y1, x2, y2], None, None, None, _round(liveness), crop))
            continue

        vec = eng.embed(bgr, face.kps)
        if vec is None:
            continue
        hits = gallery.search(vec, limit=1)
        top = hits[0] if hits else None
        if top and top.get("person_id") and top["score"] >= threshold:
            out.append(LiveFace(
                "face_recognized", [x1, y1, x2, y2], _round(top["score"]),
                str(top["person_id"]), top.get("person_name"), _round(liveness), crop,
            ))
        else:
            out.append(LiveFace("face_unknown", [x1, y1, x2, y2], None, None, None, _round(liveness), crop))
    return out


def _round(v):
    return round(float(v), 4) if v is not None else None
