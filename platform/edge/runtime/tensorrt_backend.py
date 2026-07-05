"""TensorRT backend — NVIDIA GPU-only, deliberately a STUB on this host.

TensorRT serves models as a serialized ``.engine`` file, and — this is the key
constraint — that engine is **not portable**. It is built for one specific GPU
architecture + TensorRT + CUDA/driver version. You therefore CANNOT build it on
a CPU dev laptop; you build it on (or for) the exact GPU host that will run it.

Because of that, this file intentionally stays importable on CPU (no top-level
``tensorrt``/``pycuda`` import) but ``__init__`` raises ``NotImplementedError``.
The real implementation lives on the GPU host.

Intended ONNX -> engine -> serve flow (done on the GPU box):

    1. Export/obtain the model as ``.onnx``.
    2. Build an engine for THIS GPU, e.g.::

           trtexec --onnx=model.onnx --saveEngine=model.engine --fp16

       (or programmatically via ``trt.Builder`` + ``OnnxParser``).
    3. At serve time: create a ``trt.Runtime``, ``deserialize_cuda_engine()``
       the ``.engine`` bytes, allocate input/output device buffers with pycuda,
       and run ``context.execute_v2()`` per batch — copying host<->device
       around each call. That logic replaces the ``raise`` below.
"""

from __future__ import annotations

import numpy as np

from .base import InferenceBackend


class TensorRTBackend(InferenceBackend):
    """Placeholder for the NVIDIA TensorRT engine backend.

    Kept importable on any host so the registry can reference it, but it cannot
    be instantiated off-GPU: the ``.engine`` must be built on the target GPU.
    """

    def __init__(self, model_path: str, device: str = "cuda") -> None:
        # No top-level tensorrt/pycuda import: importing this module must stay
        # safe on a CPU-only box. Instantiation is what's unsupported here.
        raise NotImplementedError(
            "TensorRT backend runs only on a GPU host; build the .engine there"
        )

    def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:  # pragma: no cover
        raise NotImplementedError(
            "TensorRT backend runs only on a GPU host; build the .engine there"
        )

    @property
    def input_names(self) -> list[str]:  # pragma: no cover
        raise NotImplementedError(
            "TensorRT backend runs only on a GPU host; build the .engine there"
        )

    @property
    def output_names(self) -> list[str]:  # pragma: no cover
        raise NotImplementedError(
            "TensorRT backend runs only on a GPU host; build the .engine there"
        )
