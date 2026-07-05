"""edge.runtime — the pluggable model-loading / inference-engine layer.

The runtime is engine-agnostic: models are described by a ``manifest.json``
and served through a common :class:`InferenceBackend` interface, so the same
family/task code runs on ONNX (CPU-first, default), OpenVINO (Intel), or
TensorRT (NVIDIA GPU) without change. The optional engines are lazy-imported,
so this package imports cleanly on a plain CPU host.

Typical use::

    from edge.runtime import load_backend
    backend, manifest = load_backend("./models/scrfd_10g")
    outputs = backend.infer({backend.input_names[0]: blob})
"""

from __future__ import annotations

from .base import InferenceBackend
from .manifest import Manifest, dump_manifest, load_manifest
from .onnx_backend import OnnxBackend
from .openvino_backend import OpenVINOBackend
from .registry import load_backend
from .tensorrt_backend import TensorRTBackend

__all__ = [
    "InferenceBackend",
    "OnnxBackend",
    "OpenVINOBackend",
    "TensorRTBackend",
    "Manifest",
    "load_manifest",
    "dump_manifest",
    "load_backend",
]
