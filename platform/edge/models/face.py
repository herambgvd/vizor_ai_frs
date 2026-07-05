"""SCRFD face detector + ArcFace/AdaFace embedder — CPU-first, ONNX.

Pre/post-processing lives here (per the runtime contract: the backend only moves
tensors; families do the letterbox/normalize/decode/align). Everything is loaded
lazily from model dirs described by a ``manifest.json``, so importing this module
never requires onnxruntime/opencv/weights to be present — callers check
``FaceEngine.available``.

Pipeline:  bgr frame → SCRFD detect (5 landmarks) → align 112×112 → embed 512-d.
Embedder family is ``arcface`` (InsightFace w600k_r50, the default fetched weights)
or ``adaface`` (drop-in): preprocessing is identical, so both share one path.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..core.config import get_settings
from ..core.logging import get_logger

log = get_logger("edge.models.face")

# Canonical 5-point face template (ArcFace/AdaFace) for a 112×112 aligned crop.
_ARCFACE_TEMPLATE = np.array(
    [[38.2946, 51.6963], [73.5318, 51.5014], [56.0252, 71.7366],
     [41.5493, 92.3655], [70.7299, 92.2041]],
    dtype=np.float32,
)


@dataclass
class Face:
    """One detected face in original-image coordinates."""

    bbox: tuple[float, float, float, float]  # x1, y1, x2, y2
    kps: np.ndarray                          # (5, 2) landmarks
    score: float

    @property
    def area(self) -> float:
        x1, y1, x2, y2 = self.bbox
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    """Plain IoU NMS over [x1,y1,x2,y2,score] rows; returns kept indices."""
    x1, y1, x2, y2, scores = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3], dets[:, 4]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[np.where(iou <= thresh)[0] + 1]
    return keep


class _SCRFD:
    """SCRFD detector wrapper (feat strides 8/16/32, 2 anchors, 5 landmarks)."""

    _STRIDES = (8, 16, 32)
    _NUM_ANCHORS = 2
    _FMC = 3  # feature map count

    def __init__(self, model_dir: str, conf: float = 0.5, nms: float = 0.4, device: str = "cpu"):
        from ..runtime.registry import load_backend

        self.backend, self.manifest = load_backend(model_dir, device=device)
        self.input_size = tuple(self.manifest.input_size)  # (w, h)
        self.conf = float(self.manifest.postprocess.get("conf_thresh", conf))
        self.nms = float(self.manifest.postprocess.get("nms_thresh", nms))
        self._out_names = self.backend.output_names
        self._in_name = self.backend.input_names[0]

    def detect(self, bgr: np.ndarray) -> list[Face]:
        import cv2

        iw, ih = self.input_size
        h0, w0 = bgr.shape[:2]
        scale = min(iw / w0, ih / h0)
        nw, nh = int(round(w0 * scale)), int(round(h0 * scale))
        resized = cv2.resize(bgr, (nw, nh))
        canvas = np.zeros((ih, iw, 3), dtype=np.uint8)
        canvas[:nh, :nw] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1.0 / 128, (iw, ih), (127.5, 127.5, 127.5), swapRB=True)
        outs = self.backend.infer({self._in_name: blob.astype(np.float32)})
        net = [outs[n] for n in self._out_names]

        scores_l, boxes_l, kps_l = [], [], []
        for idx, stride in enumerate(self._STRIDES):
            scores = net[idx].reshape(-1)
            bbox_preds = net[idx + self._FMC].reshape(-1, 4) * stride
            kps_preds = net[idx + self._FMC * 2].reshape(-1, 10) * stride
            gh, gw = ih // stride, iw // stride
            ax, ay = np.meshgrid(np.arange(gw), np.arange(gh))
            centers = np.stack([ax, ay], axis=-1).astype(np.float32).reshape(-1, 2) * stride
            centers = np.repeat(centers, self._NUM_ANCHORS, axis=0)
            keep = np.where(scores >= self.conf)[0]
            if keep.size == 0:
                continue
            c = centers[keep]
            bp = bbox_preds[keep]
            x1 = c[:, 0] - bp[:, 0]; y1 = c[:, 1] - bp[:, 1]
            x2 = c[:, 0] + bp[:, 2]; y2 = c[:, 1] + bp[:, 3]
            boxes_l.append(np.stack([x1, y1, x2, y2], axis=1))
            scores_l.append(scores[keep])
            kp = kps_preds[keep].reshape(-1, 5, 2)
            kp[:, :, 0] += c[:, 0:1]
            kp[:, :, 1] += c[:, 1:2]
            kps_l.append(kp)

        if not boxes_l:
            return []
        boxes = np.vstack(boxes_l) / scale
        scores = np.concatenate(scores_l)
        kpss = np.vstack(kps_l) / scale
        dets = np.hstack([boxes, scores[:, None]]).astype(np.float32)
        keep = _nms(dets, self.nms)
        faces = []
        for i in keep:
            x1, y1, x2, y2 = boxes[i]
            faces.append(Face(bbox=(float(x1), float(y1), float(x2), float(y2)),
                              kps=kpss[i], score=float(scores[i])))
        return faces


class _Embedder:
    """ArcFace/AdaFace 512-d embedder (aligned 112×112 → L2-normalised vector)."""

    def __init__(self, model_dir: str, device: str = "cpu"):
        from ..runtime.registry import load_backend

        self.backend, self.manifest = load_backend(model_dir, device=device)
        self.family = self.manifest.family
        self.dim = int(self.manifest.embed_dim or 512)
        self._swap_rb = bool(self.manifest.preprocess.get("swap_rb", True))
        self._in_name = self.backend.input_names[0]
        self._out_name = self.backend.output_names[0]

    def align(self, bgr: np.ndarray, kps: np.ndarray) -> np.ndarray:
        import cv2

        M, _ = cv2.estimateAffinePartial2D(kps.astype(np.float32), _ARCFACE_TEMPLATE, method=cv2.LMEDS)
        return cv2.warpAffine(bgr, M, (112, 112), borderValue=0.0)

    def embed(self, bgr: np.ndarray, kps: np.ndarray) -> np.ndarray:
        import cv2

        aligned = self.align(bgr, kps)
        blob = cv2.dnn.blobFromImage(aligned, 1.0 / 127.5, (112, 112), (127.5, 127.5, 127.5), swapRB=self._swap_rb)
        out = self.backend.infer({self._in_name: blob.astype(np.float32)})[self._out_name]
        vec = np.asarray(out).reshape(-1).astype(np.float32)
        norm = np.linalg.norm(vec) or 1.0
        return vec / norm


class _PAD:
    """Presentation-attack-detection (anti-spoof) classifier over a face crop.

    Model-agnostic + manifest-driven, like the detector/embedder: it reads
    ``input_size`` and normalization from the model's ``manifest.json`` and returns
    a liveness probability in [0, 1] (higher = more likely a live face). Defaults
    match the common MiniFASNet / Silent-Face family (80×80, /255, softmax with the
    live class last), overridable via ``manifest.postprocess``.
    """

    def __init__(self, model_dir: str, device: str = "cpu"):
        from ..runtime.registry import load_backend

        self.backend, self.manifest = load_backend(model_dir, device=device)
        self.input_size = tuple(self.manifest.input_size or (80, 80))  # (w, h)
        self._swap_rb = bool(self.manifest.preprocess.get("swap_rb", True))
        self._scale = float(self.manifest.preprocess.get("scale", 1.0 / 255.0))
        pp = self.manifest.postprocess or {}
        # Index of the "live/real" class in the model's output vector.
        self._live_index = int(pp.get("live_index", -1))
        self._apply_softmax = bool(pp.get("softmax", True))
        # Crop the face box out with this margin before classifying (spoof cues
        # live in the surrounding context — screen bezel, paper edge).
        self._margin = float(pp.get("crop_margin", 0.0))
        self._in_name = self.backend.input_names[0]
        self._out_name = self.backend.output_names[0]

    def score(self, bgr: np.ndarray, bbox: tuple[float, float, float, float]) -> float:
        import cv2

        h0, w0 = bgr.shape[:2]
        x1, y1, x2, y2 = bbox
        bw, bh = x2 - x1, y2 - y1
        mx, my = bw * self._margin, bh * self._margin
        cx1, cy1 = max(0, int(x1 - mx)), max(0, int(y1 - my))
        cx2, cy2 = min(w0, int(x2 + mx)), min(h0, int(y2 + my))
        crop = bgr[cy1:cy2, cx1:cx2]
        if crop.size == 0:
            return 0.0
        iw, ih = self.input_size
        blob = cv2.dnn.blobFromImage(crop, self._scale, (iw, ih), (0, 0, 0), swapRB=self._swap_rb)
        out = np.asarray(self.backend.infer({self._in_name: blob.astype(np.float32)})[self._out_name])
        vec = out.reshape(-1).astype(np.float64)
        if self._apply_softmax:
            e = np.exp(vec - vec.max())
            vec = e / (e.sum() or 1.0)
        return float(vec[self._live_index])


class FaceEngine:
    """Lazy-loading detector + embedder (+ optional PAD). ``available`` is False
    until the weights AND onnxruntime/opencv are importable — callers degrade
    gracefully. PAD is independent: it stays unavailable until a model is dropped
    at ``{model_dir}/pad`` and ``pad_enabled`` is set."""

    def __init__(self, scrfd_dir: str, embed_dir: str, pad_dir: str | None = None, device: str = "cpu"):
        self._scrfd_dir = scrfd_dir
        self._embed_dir = embed_dir
        self._pad_dir = pad_dir
        self._device = device
        self._det: _SCRFD | None = None
        self._emb: _Embedder | None = None
        self._pad: _PAD | None = None
        self._pad_error: str | None = None
        self._load_error: str | None = None

    def _ensure(self) -> bool:
        if self._det is not None and self._emb is not None:
            return True
        if self._load_error is not None:
            return False
        try:
            self._det = _SCRFD(self._scrfd_dir, device=self._device)
            self._emb = _Embedder(self._embed_dir, device=self._device)
            log.info(
                "face engine loaded scrfd=%s embed=%s(%s) device=%s",
                self._scrfd_dir, self._embed_dir, self._emb.family, self._device,
            )
            return True
        except Exception as exc:  # weights missing, onnxruntime/opencv absent, bad manifest
            self._load_error = str(exc)
            log.warning("face engine unavailable: %s", exc)
            return False

    @property
    def available(self) -> bool:
        return self._ensure()

    def _ensure_pad(self) -> bool:
        if self._pad is not None:
            return True
        if self._pad_error is not None or not self._pad_dir:
            return False
        try:
            self._pad = _PAD(self._pad_dir, device=self._device)
            log.info("PAD (anti-spoof) model loaded from %s", self._pad_dir)
            return True
        except Exception as exc:  # no model dropped in yet, or bad manifest
            self._pad_error = str(exc)
            log.warning("PAD model unavailable: %s", exc)
            return False

    @property
    def pad_available(self) -> bool:
        return self._ensure_pad()

    def liveness(self, bgr: np.ndarray, face: Face) -> float | None:
        """Liveness probability [0,1] for a detected face, or None if no PAD model."""
        if not self._ensure_pad():
            return None
        return self._pad.score(bgr, face.bbox)

    @property
    def status(self) -> dict:
        ok = self._ensure()
        return {
            "available": ok,
            "device": self._device,
            "embedder_family": self._emb.family if self._emb else None,
            "embed_dim": self._emb.dim if self._emb else None,
            "error": self._load_error,
            "pad_available": self._ensure_pad(),
            "pad_error": self._pad_error,
        }

    @property
    def model_id(self) -> str:
        """Version tag stored on each faceprint so we can migrate embedders later."""
        return self._emb.family if self._emb else "none"

    @property
    def embed_dim(self) -> int:
        return self._emb.dim if self._emb else 512

    def detect(self, bgr: np.ndarray) -> list[Face]:
        if not self._ensure():
            return []
        return self._det.detect(bgr)

    def embed(self, bgr: np.ndarray, kps: np.ndarray) -> np.ndarray | None:
        if not self._ensure():
            return None
        return self._emb.embed(bgr, kps)

    def largest_face(self, bgr: np.ndarray) -> Face | None:
        faces = self.detect(bgr)
        return max(faces, key=lambda f: f.area) if faces else None

    def detect_and_embed(self, bgr: np.ndarray) -> list[tuple[Face, np.ndarray]]:
        out = []
        for f in self.detect(bgr):
            v = self.embed(bgr, f.kps)
            if v is not None:
                out.append((f, v))
        return out


@lru_cache(maxsize=1)
def get_face_engine() -> FaceEngine:
    """Process-wide FaceEngine using ``{model_dir}/scrfd`` and ``{model_dir}/embed``.

    The inference device comes from ``settings.inference_device`` ("cpu" | "cuda").
    """
    settings = get_settings()
    base = Path(settings.model_dir)
    return FaceEngine(
        str(base / "scrfd"),
        str(base / "embed"),
        pad_dir=str(base / "pad"),
        device=settings.inference_device,
    )
