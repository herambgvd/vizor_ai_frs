"""Backend registry — turn a model directory into a ready-to-run backend.

This is the one function most callers actually use. Given a model directory it:

    1. reads ``manifest.json`` (via :func:`load_manifest`),
    2. resolves the weights path relative to that directory,
    3. picks the concrete backend class from ``manifest.backend``,
    4. constructs + returns ``(backend, manifest)``.

It also keeps a tiny in-process cache keyed by the resolved model directory, so
loading the same model twice (e.g. two request handlers) reuses one backend /
one loaded session instead of paying the (expensive) construction cost again.
"""

from __future__ import annotations

from pathlib import Path

from edge.core.config import get_settings
from edge.core.logging import get_logger

from .base import InferenceBackend
from .manifest import Manifest, load_manifest
from .onnx_backend import OnnxBackend
from .openvino_backend import OpenVINOBackend
from .tensorrt_backend import TensorRTBackend

log = get_logger("edge.runtime.registry")

# Process-local cache: resolved model dir (str) -> (backend, manifest).
# Small and intentional — one entry per distinct model served by this process.
_CACHE: dict[str, tuple[InferenceBackend, Manifest]] = {}


def load_backend(
    model_dir: str | Path,
    *,
    settings=None,
    device: str = "cpu",
) -> tuple[InferenceBackend, Manifest]:
    """Load (or reuse) the backend for the model in ``model_dir``.

    Args:
        model_dir: directory containing ``manifest.json`` + the weights file.
        settings: optional settings object (defaults to
            :func:`edge.core.config.get_settings`). Reserved for future use /
            testability; the manifest already carries per-model config.
        device: "cpu" (default) or e.g. "cuda". For the ONNX backend, a
            non-cpu device switches on the CUDA execution provider (with a CPU
            fallback). Ignored by the OpenVINO/TensorRT stubs beyond their own
            device handling.

    Returns:
        ``(backend, manifest)``.

    Raises:
        ValueError: if the manifest names an unknown backend.
    """
    if settings is None:
        settings = get_settings()

    # Resolve to an absolute, canonical path so the cache key is stable
    # regardless of how the caller spelled the directory.
    resolved = Path(model_dir).resolve()
    cache_key = str(resolved)

    cached = _CACHE.get(cache_key)
    if cached is not None:
        log.debug("reusing cached backend for %s", cache_key)
        return cached

    manifest = load_manifest(resolved / "manifest.json")
    weights_path = str(resolved / manifest.weights)

    log.info(
        "loading model dir=%s family=%s task=%s backend=%s device=%s",
        cache_key, manifest.family, manifest.task, manifest.backend, device,
    )

    if manifest.backend == "onnx":
        # CPU-first: only request the CUDA provider when explicitly on GPU,
        # always keeping CPU as a fallback so a missing GPU degrades gracefully.
        if device != "cpu":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
        backend: InferenceBackend = OnnxBackend(weights_path, providers=providers)
    elif manifest.backend == "openvino":
        backend = OpenVINOBackend(weights_path)
    elif manifest.backend == "tensorrt":
        backend = TensorRTBackend(weights_path, device=device)
    else:  # defensive: load_manifest already validates, but never trust silently
        raise ValueError(f"unknown backend '{manifest.backend}' in {cache_key}")

    result = (backend, manifest)
    _CACHE[cache_key] = result
    return result


def clear_cache() -> None:
    """Drop all cached backends (useful in tests or after model swaps)."""
    _CACHE.clear()
