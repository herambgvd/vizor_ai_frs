"""Face enrollment pipeline: image → SCRFD detect → align → ArcFace embed →
quality/liveness gates → duplicate guard → Qdrant gallery upsert (+ augments).

Sync CPU/ONNX work — callers run it in a threadpool off the async request path.
Reuses the shared platform FaceEngine (SCRFD + ArcFace, optional PAD liveness).
Never raises: returns a status dict so a photo row is always recorded.
"""

from __future__ import annotations

import uuid

import numpy as np

from edge.core.logging import get_logger

from . import gallery
from .recognition import get_engine

log = get_logger("frs.enroll")

# Reject a new photo if a DIFFERENT person is already this cosine-similar.
DUP_COSINE = 0.62
# Enrollment anti-spoof gate — global module constants (enrollment thresholds are
# NOT per-camera and NOT exposed in the UI; vizor_nvr parity).
PAD_ENABLED = False
LIVENESS_THRESHOLD = 0.5
# Photometric augment factors (brightness) — fallback augments when the engine
# can't hand back an aligned crop for the proven photometric-variant path.
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
    eng = get_engine()
    if not eng.available:
        return None
    try:
        bgr = _decode(img_bytes)
    except ValueError:
        return None
    face = eng.largest_face(bgr)
    if face is None:
        return None
    # Query/forensic embedding: align + ArcFace, no denoise (enroll parity).
    return eng.embed_face(bgr, face, denoise=False)


def enroll_photo(img_bytes: bytes, *, person_id, photo_id, person_name: str = "") -> dict:
    """Detect + embed the largest face and upsert it into the gallery.

    Returns a dict with ``status`` in {enrolled, failed} plus scores / error.
    """
    dup_cosine = DUP_COSINE
    pad_enabled = PAD_ENABLED
    liveness_threshold = LIVENESS_THRESHOLD
    eng = get_engine()
    if not eng.available:
        return {"status": "failed", "error_code": "models_unavailable", "error": "face models not loaded"}
    try:
        bgr = _decode(img_bytes)
    except ValueError as exc:
        return {"status": "failed", "error_code": "bad_image", "error": str(exc)}

    face = eng.largest_face(bgr)
    if face is None:
        return {"status": "failed", "error_code": "no_face", "error": "no face detected in the photo"}
    # Align once (recovering geometry via YuNet when SCRFD landmarks are degenerate)
    # and reuse the aligned crop for both the embedding and the photometric augments.
    # No denoise on the enroll path (reference parity). ``aligned`` is None on the
    # edge CPU backend, which falls back to brightness augments below.
    aligned = eng.align_crop(bgr, face, denoise=False)
    vec = eng.embed_aligned(aligned) if aligned is not None else eng.embed_face(bgr, face, denoise=False)
    if vec is None:
        return {"status": "failed", "error_code": "embed_failed", "error": "could not embed the face"}

    liveness = eng.liveness(bgr, face)
    if pad_enabled and liveness is not None and liveness < liveness_threshold:
        return {
            "status": "failed", "error_code": "spoof",
            "error": "liveness check failed (possible photo/screen)",
            "liveness_score": round(float(liveness), 4),
        }

    # Duplicate guard — a different person must not already own this face.
    for hit in gallery.search(vec, limit=3):
        if hit.get("person_id") and str(hit["person_id"]) != str(person_id) and hit["score"] >= dup_cosine:
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
    if aligned is not None:
        # Proven photometric-variant augments (brightness/contrast/gamma/flip/scale/
        # geometric) on the aligned crop — boost CCTV recall without a re-detect.
        from .recognition.augment import generate_photometric_variants

        for var in generate_photometric_variants(aligned):
            v2 = eng.embed_aligned(var["image"])
            if v2 is None:
                continue
            gallery.upsert(str(uuid.uuid4()), v2, {**base, "synthetic": True, "augment": var["tag"]})
            augments += 1
    else:
        # Edge CPU backend can't hand back an aligned crop → brightness augments.
        for factor in _AUGMENTS:
            aug = cv2.convertScaleAbs(bgr, alpha=factor, beta=0)
            f2 = eng.largest_face(aug)
            if f2 is None:
                continue
            v2 = eng.embed_face(aug, f2, denoise=False)
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
