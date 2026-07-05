"""OpenVINO backend — Intel CPU/iGPU/VPU acceleration.

IMPORTANT: ``openvino`` is an OPTIONAL heavy dependency. It is NOT installed by
default and must never be imported at module top level, otherwise merely
importing ``edge.runtime`` on a plain CPU/dev box would blow up. We therefore
LAZY-import it inside ``__init__``: the class is always importable, but you only
pay the cost (and need the package) if you actually instantiate this backend.

Install it separately (``pip install openvino``) on hosts where you want to
serve models through the OpenVINO runtime. OpenVINO can read either its own IR
(``.xml`` + ``.bin``) or an ``.onnx`` file directly via ``compile_model``.
"""

from __future__ import annotations

import numpy as np

from edge.core.logging import get_logger

from .base import InferenceBackend

log = get_logger("edge.runtime.openvino")


class OpenVINOBackend(InferenceBackend):
    """Runs a model through Intel's OpenVINO runtime.

    Args:
        model_path: path to an OpenVINO IR ``.xml`` or an ``.onnx`` file.
        device: OpenVINO device string ("CPU", "GPU", "AUTO", ...). Defaults to
            CPU to stay consistent with the rest of the CPU-first runtime.
    """

    def __init__(self, model_path: str, device: str = "CPU") -> None:
        # LAZY import: keeps `import edge.runtime` clean on machines without the
        # optional openvino package. Raise a clear error if it's missing.
        try:
            import openvino as ov
        except ImportError as exc:  # pragma: no cover - depends on host packages
            raise ImportError(
                "OpenVINOBackend requires the optional 'openvino' package. "
                "Install it with `pip install openvino`."
            ) from exc

        self._model_path = model_path
        self._device = device

        log.info("compiling OpenVINO model %s (device=%s)", model_path, device)
        core = ov.Core()
        # compile_model reads + optimizes the graph for the target device once.
        self._compiled = core.compile_model(model_path, device)

        # Map friendly tensor names <-> OpenVINO port objects. A port can expose
        # several names; we take the first stable one and fall back to a
        # positional label so the contract always has usable string keys.
        self._inputs = list(self._compiled.inputs)
        self._outputs = list(self._compiled.outputs)
        self._input_names = [self._port_name(p, "input", i) for i, p in enumerate(self._inputs)]
        self._output_names = [self._port_name(p, "output", i) for i, p in enumerate(self._outputs)]

    @staticmethod
    def _port_name(port, kind: str, index: int) -> str:
        """Best-effort human name for an OpenVINO input/output port."""
        try:
            names = port.get_names()
            if names:
                return next(iter(names))
        except Exception:  # pragma: no cover - defensive; some ports lack names
            pass
        return f"{kind}_{index}"

    def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        # OpenVINO accepts a positional list keyed by input order. Reorder the
        # incoming name->array dict to match the compiled model's input order.
        ordered = [feeds[name] for name in self._input_names]
        results = self._compiled(ordered)
        # `results` is keyed by output port; remap to our string output names.
        return {
            name: np.asarray(results[port])
            for name, port in zip(self._output_names, self._outputs)
        }

    @property
    def input_names(self) -> list[str]:
        return self._input_names

    @property
    def output_names(self) -> list[str]:
        return self._output_names
