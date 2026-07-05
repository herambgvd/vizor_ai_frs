"""Face enrollment pipeline: image → SCRFD detect → align → ArcFace embed →
quality/liveness gates → duplicate guard → Qdrant gallery upsert (+ augments).

Sync CPU/ONNX work — callers run it in a threadpool off the async request path.
Reuses the shared platform FaceEngine (SCRFD + ArcFace, optional PAD liveness).
Never raises: returns a status dict so a photo row is always recorded.
"""

from __future__ import annotations

import uuid

import numpy as np

from edge.core.config import get_settings
from edge.core.logging import get_logger
from edge.models import get_face_engine

from . import gallery

log = get_logger("frs.enroll")

# Reject a new photo if a DIFFERENT person is already this cosine-similar.
DUP_COSINE = 0.62
# Photometric augment factors (brightness) — improve CCTV recall.
_AUGMENTS = (0.82, 1.18)


def _decode(img_bytes: bytes):
    import cv2

    bgr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("could not decode image")
    return bgr


def embed_query(img_bytes: bytes):
    """Embed the largest face in a probe image (no quality gating) for forensic
    search. Returns a 512-d vector or None if models/face are unavailable."""
    eng = get_face_engine()
    if not eng.available:
        return None
    try:
        bgr = _decode(img_bytes)
    except ValueError:
        return None
    face = eng.largest_face(bgr)
    if face is None:
        return None
    return eng.embed(bgr, face.kps)


def enroll_photo(img_bytes: bytes, *, person_id, photo_id, person_name: str = "") -> dict:
    """Detect + embed the largest face and upsert it into the gallery.

    Returns a dict with ``status`` in {enrolled, failed} plus scores / error.
    """
    eng = get_face_engine()
    if not eng.available:
        return {"status": "failed", "error_code": "models_unavailable", "error": "face models not loaded"}
    try:
        bgr = _decode(img_bytes)
    except ValueError as exc:
        return {"status": "failed", "error_code": "bad_image", "error": str(exc)}

    face = eng.largest_face(bgr)
    if face is None:
        return {"status": "failed", "error_code": "no_face", "error": "no face detected in the photo"}
    vec = eng.embed(bgr, face.kps)
    if vec is None:
        return {"status": "failed", "error_code": "embed_failed", "error": "could not embed the face"}

    settings = get_settings()
    liveness = eng.liveness(bgr, face)
    if settings.pad_enabled and liveness is not None and liveness < settings.pad_threshold:
        return {
            "status": "failed", "error_code": "spoof",
            "error": "liveness check failed (possible photo/screen)",
            "liveness_score": round(float(liveness), 4),
        }

    # Duplicate guard — a different person must not already own this face.
    for hit in gallery.search(vec, limit=3):
        if hit.get("person_id") and str(hit["person_id"]) != str(person_id) and hit["score"] >= DUP_COSINE:
            return {
                "status": "failed", "error_code": "duplicate",
                "error": f"this face matches another person ({hit.get('person_name') or 'unknown'})",
            }

    # Sharpness (Laplacian variance) for a quality signal.
    import cv2

    x1, y1, x2, y2 = (int(v) for v in face.bbox)
    crop = bgr[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
    sharp = float(cv2.Laplacian(crop, cv2.CV_64F).var()) if crop.size else 0.0

    base = {"person_id": str(person_id), "person_name": person_name, "point_key": str(photo_id), "type": "photo"}
    gallery.upsert(str(uuid.uuid4()), vec, {**base, "synthetic": False})

    augments = 0
    for factor in _AUGMENTS:
        aug = cv2.convertScaleAbs(bgr, alpha=factor, beta=0)
        f2 = eng.largest_face(aug)
        if f2 is None:
            continue
        v2 = eng.embed(aug, f2.kps)
        if v2 is None:
            continue
        gallery.upsert(str(uuid.uuid4()), v2, {**base, "synthetic": True, "augment": f"bright_{factor}"})
        augments += 1

    return {
        "status": "enrolled",
        "embedding_id": str(photo_id),
        "quality_score": round(float(face.score), 4),
        "liveness_score": round(float(liveness), 4) if liveness is not None else None,
        "sharpness_score": round(sharp, 2),
        "augments": augments,
    }
