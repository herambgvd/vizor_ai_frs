"""Recognition-engine accessor.

``get_engine()`` returns a lazily-built, process-wide face engine exposing a
uniform surface (``available`` / ``detect`` / ``largest_face`` / ``embed`` /
``embed_face`` / ``liveness`` / ``age_gender``):

* ``VE_INFERENCE_BACKEND=triton`` (default) → :class:`TritonFaceEngine`, pointed at
  ``VE_TRITON_URL`` (default ``vizor-triton:8000``). Shared GPU Triton, batched.
* anything else, or if Triton wiring can't be built → the edge CPU ``FaceEngine``
  (``edge.models.get_face_engine``), wrapped so ``embed_face`` still works, so CPU
  dev keeps running.

Import-safe and defensive: never raises at import time, and never raises from
``get_engine()`` — a fully unavailable engine degrades to ``available == False``.
"""
from __future__ import annotations

import os
import threading

try:
    from edge.core.logging import get_logger
    log = get_logger("frs.recognition")
except Exception:  # noqa: BLE001 — logging is optional at import time
    import logging
    log = logging.getLogger("frs.recognition")

_engine = None
_lock = threading.Lock()


class _Unavailable:
    """Null engine — used only when NO backend could be constructed."""

    available = False

    def status(self) -> dict:
        return {"backend": "none", "available": False}

    def detect(self, bgr, conf_thresh: float = 0.5):
        return []

    def largest_face(self, bgr):
        return None

    def align_crop(self, bgr, face, *, denoise: bool = False):
        return None

    def embed_aligned(self, aligned):
        return None

    def embed_face(self, bgr, face, *, denoise: bool = True):
        return None

    def embed(self, bgr, kps, *, denoise: bool = True):
        return None

    def liveness(self, bgr, face):
        return None

    def age_gender(self, bgr, face):
        return None


def _bool_env(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _build():
    backend = os.getenv("VE_INFERENCE_BACKEND", "triton").strip().lower()
    if backend == "triton":
        try:
            from .faceengine import TritonFaceEngine

            url = os.getenv("VE_TRITON_URL", "vizor-triton:8000")
            has_fairface = _bool_env("VE_TRITON_HAS_FAIRFACE", True)
            has_antispoof = _bool_env("VE_TRITON_HAS_ANTISPOOF", False)
            eng = TritonFaceEngine(url, has_fairface=has_fairface, has_antispoof=has_antispoof)
            log.info("recognition backend: triton url=%s fairface=%s antispoof=%s",
                     url, has_fairface, has_antispoof)
            return eng
        except Exception as exc:  # noqa: BLE001
            log.warning("triton face engine unavailable, falling back to edge: %s", exc)

    # CPU dev fallback — edge FaceEngine, wrapped for a uniform embed_face surface.
    try:
        from edge.models import get_face_engine

        from .faceengine import EdgeFaceEngineAdapter

        log.info("recognition backend: edge FaceEngine (cpu)")
        return EdgeFaceEngineAdapter(get_face_engine())
    except Exception as exc:  # noqa: BLE001
        log.warning("no recognition backend available: %s", exc)
        return _Unavailable()


def get_engine():
    """Process-singleton face engine. Never raises; may be ``available == False``."""
    global _engine
    if _engine is not None:
        return _engine
    with _lock:
        if _engine is None:
            _engine = _build()
    return _engine
