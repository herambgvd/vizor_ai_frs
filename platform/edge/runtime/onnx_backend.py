"""ONNX Runtime backend — the default, CPU-first engine.

``onnxruntime`` is a hard dependency of this project (it's installed), so we
import it at the top. This backend is the reference implementation: it loads a
``.onnx`` file into an ``InferenceSession`` and runs it. The same session
transparently uses the CPU or the GPU depending on the execution providers we
hand it, so this one class covers both the dev laptop and a CUDA edge box.
"""

from __future__ import annotations

import numpy as np
import onnxruntime as ort

from edge.core.logging import get_logger

from .base import InferenceBackend

log = get_logger("edge.runtime.onnx")


class OnnxBackend(InferenceBackend):
    """Runs an ONNX graph via onnxruntime.

    Args:
        model_path: filesystem path to the ``.onnx`` weights file.
        providers: ordered list of ONNX Runtime execution providers. Defaults
            to CPU-only. Pass e.g. ``["CUDAExecutionProvider",
            "CPUExecutionProvider"]`` to prefer the GPU with a CPU fallback.
    """

    def __init__(self, model_path: str, providers: list[str] | None = None) -> None:
        # CPU-first: without an explicit request we never touch a GPU provider,
        # so the backend behaves identically on a dev box with no CUDA.
        if providers is None:
            providers = ["CPUExecutionProvider"]

        self._model_path = model_path
        self._providers = providers

        log.info("loading ONNX model %s (providers=%s)", model_path, providers)
        # The session compiles + memory-plans the graph once, here, so repeated
        # infer() calls are cheap. Construction is the expensive part.
        self._session = ort.InferenceSession(model_path, providers=providers)

        # Cache the tensor names now so we don't re-walk the graph metadata on
        # every call. Order matters (families rely on positional outputs).
        self._input_names: list[str] = [i.name for i in self._session.get_inputs()]
        self._output_names: list[str] = [o.name for o in self._session.get_outputs()]

    def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        # session.run(output_names, feeds) returns a list aligned with
        # output_names; we zip it back into a name->array dict to satisfy the
        # InferenceBackend contract.
        outputs = self._session.run(self._output_names, feeds)
        return dict(zip(self._output_names, outputs))

    @property
    def input_names(self) -> list[str]:
        return self._input_names

    @property
    def output_names(self) -> list[str]:
        return self._output_names
