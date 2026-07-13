"""Triton-backed FaceEngine adapter.

Exposes the SAME surface the edge ``FaceEngine`` gives the recognition modules
(``available`` / ``detect`` / ``largest_face`` / ``embed`` / ``liveness`` /
``age_gender``) on top of the shared-Triton :class:`TritonEngine`. Detection maps
Triton's dict output to lightweight :class:`Face` objects; embedding goes through
the proven align → (optional NLM denoise) → ArcFace path (``align.align_face``,
which already applies ``_landmarks_sane`` + YuNet recovery internally), exactly
mirroring the reference vizor_nvr recognition service.

Also provides :class:`EdgeFaceEngineAdapter`, a thin wrapper that gives the edge
CPU ``FaceEngine`` the same ``embed_face`` / ``align_crop`` / ``embed_aligned``
surface so enroll/live can be backend-agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .align import align_face, denoise_face
from .quality import crop_face_with_margin
from .triton_engine import TritonEngine


@dataclass
class Face:
    """One detected face in original-image coordinates (edge-FaceEngine parity)."""

    bbox: tuple           # (x1, y1, x2, y2)
    kps: np.ndarray       # (5, 2) landmarks (may be None)
    score: float

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


class TritonFaceEngine:
    """Edge-FaceEngine-compatible surface implemented on top of TritonEngine."""

    def __init__(self, url: str, has_fairface: bool = True, has_antispoof: bool = False,
                 timeout: float = 30.0):
        self._eng = TritonEngine(url, has_fairface=has_fairface,
                                 has_antispoof=has_antispoof, timeout=timeout)

    # ── readiness ──────────────────────────────────────────────────────────
    @property
    def available(self) -> bool:
        try:
            return bool(self._eng.ready)
        except Exception:  # noqa: BLE001
            return False

    def status(self) -> dict:
        try:
            return self._eng.status()
        except Exception as exc:  # noqa: BLE001
            return {"backend": "triton", "ready": False, "error": str(exc)[:200]}

    # ── detection ──────────────────────────────────────────────────────────
    def detect(self, bgr, conf_thresh: float = 0.5) -> list[Face]:
        try:
            dets = self._eng.detect_faces(bgr, conf_thresh=conf_thresh)
        except Exception:  # noqa: BLE001
            return []
        out: list[Face] = []
        for d in dets:
            bb = d["bbox"]
            out.append(Face(
                bbox=(float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])),
                kps=d.get("landmarks"),
                score=float(d.get("confidence", 0.0)),
            ))
        return out

    def largest_face(self, bgr) -> Face | None:
        faces = self.detect(bgr)
        return max(faces, key=lambda f: f.area) if faces else None

    # ── alignment + embedding ──────────────────────────────────────────────
    def align_crop(self, bgr, face: Face, *, denoise: bool = False):
        """Return the 112x112 aligned ArcFace crop for a detected face (or None)."""
        if bgr is None or face is None:
            return None
        h, w = bgr.shape[:2]
        bbox = np.asarray(face.bbox, dtype=np.float32)
        kps = np.asarray(face.kps, dtype=np.float32) if face.kps is not None else None
        aligned = align_face(bgr, bbox, kps, w, h)
        if denoise:
            aligned = denoise_face(aligned)
        return aligned

    def embed_aligned(self, aligned) -> np.ndarray | None:
        """Embed an already-aligned 112x112 crop (used for augment variants)."""
        if aligned is None:
            return None
        return self._eng.embed_face(aligned)

    def embed_face(self, bgr, face: Face, *, denoise: bool = True) -> np.ndarray | None:
        """Align (recovering geometry via YuNet when needed) then ArcFace-embed.

        ``denoise`` mirrors the reference: the live path denoises the aligned crop,
        the enroll/query path does not."""
        aligned = self.align_crop(bgr, face, denoise=denoise)
        return self.embed_aligned(aligned)

    def embed(self, bgr, kps, *, denoise: bool = True) -> np.ndarray | None:
        """edge-FaceEngine parity: embed from landmarks alone (bbox recovered from
        the landmark extent). Callers with a Face should prefer ``embed_face``."""
        if kps is None:
            return None
        kps = np.asarray(kps, dtype=np.float32)
        x1, y1 = kps.min(axis=0)
        x2, y2 = kps.max(axis=0)
        face = Face(bbox=(float(x1), float(y1), float(x2), float(y2)), kps=kps, score=1.0)
        return self.embed_face(bgr, face, denoise=denoise)

    # ── liveness / demographics ────────────────────────────────────────────
    def liveness(self, bgr, face: Face) -> float | None:
        if bgr is None or face is None:
            return None
        h, w = bgr.shape[:2]
        try:
            crop = crop_face_with_margin(bgr, np.asarray(face.bbox, dtype=np.float32), w, h)
            return self._eng.liveness(crop)
        except Exception:  # noqa: BLE001
            return None

    def age_gender(self, bgr, face: Face):
        if bgr is None or face is None:
            return None
        h, w = bgr.shape[:2]
        try:
            crop = crop_face_with_margin(bgr, np.asarray(face.bbox, dtype=np.float32), w, h)
            return self._eng.age_gender(crop)
        except Exception:  # noqa: BLE001
            return None


class EdgeFaceEngineAdapter:
    """Wrap the edge CPU FaceEngine so enroll/live can call ``embed_face`` uniformly.

    The edge engine has no align-crop / pre-aligned-embed surface (it aligns
    internally inside ``embed``), so ``align_crop`` / ``embed_aligned`` return None
    and enroll falls back to its brightness augments on this backend."""

    def __init__(self, eng):
        self._eng = eng

    @property
    def available(self) -> bool:
        try:
            return bool(self._eng.available)
        except Exception:  # noqa: BLE001
            return False

    def status(self) -> dict:
        try:
            return dict(self._eng.status)
        except Exception:  # noqa: BLE001
            return {"backend": "edge", "available": self.available}

    def detect(self, bgr, conf_thresh: float = 0.5):
        try:
            return self._eng.detect(bgr)
        except Exception:  # noqa: BLE001
            return []

    def largest_face(self, bgr):
        try:
            return self._eng.largest_face(bgr)
        except Exception:  # noqa: BLE001
            return None

    def align_crop(self, bgr, face, *, denoise: bool = False):
        return None

    def embed_aligned(self, aligned):
        return None

    def embed_face(self, bgr, face, *, denoise: bool = True):
        if face is None or face.kps is None:
            return None
        try:
            return self._eng.embed(bgr, np.asarray(face.kps, dtype=np.float32))
        except Exception:  # noqa: BLE001
            return None

    def embed(self, bgr, kps, *, denoise: bool = True):
        if kps is None:
            return None
        try:
            return self._eng.embed(bgr, np.asarray(kps, dtype=np.float32))
        except Exception:  # noqa: BLE001
            return None

    def liveness(self, bgr, face):
        try:
            return self._eng.liveness(bgr, face)
        except Exception:  # noqa: BLE001
            return None

    def age_gender(self, bgr, face):
        return None
