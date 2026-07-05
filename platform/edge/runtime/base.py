"""The inference-backend interface.

This is the PINNED CONTRACT for the whole runtime layer. Every concrete
backend (ONNX / OpenVINO / TensorRT) implements exactly this surface, and
everything downstream (families, tasks, the registry) is written against
``InferenceBackend`` — never against a specific engine. That's what lets us
swap engines per host (CPU dev box vs. GPU edge box) without touching model
code.

The contract is deliberately tiny and framework-agnostic:

  * inputs  ("feeds")  are a ``{name: ndarray}`` dict
  * outputs           are a ``{name: ndarray}`` dict

i.e. it mirrors the way ONNX Runtime already talks. Preprocessing (letterbox,
normalize, NCHW transpose) and postprocessing (decode boxes, L2-normalize
embeddings) live OUTSIDE the backend — the backend just moves tensors through
the graph.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class InferenceBackend(ABC):
    """Abstract engine that runs a single model graph.

    Implementations must be import-clean on a CPU-only host: any heavy or
    GPU-only dependency (openvino, tensorrt, pycuda) has to be imported LAZILY
    inside ``__init__`` / methods, never at module top level.
    """

    @abstractmethod
    def infer(self, feeds: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Run one forward pass.

        Args:
            feeds: mapping of input tensor name -> input array. The caller is
                responsible for shape/dtype correctness (this is the raw graph
                interface, so no implicit preprocessing happens here).

        Returns:
            Mapping of output tensor name -> output array.
        """
        ...

    @property
    @abstractmethod
    def input_names(self) -> list[str]:
        """Ordered names of the model's input tensors."""
        ...

    @property
    @abstractmethod
    def output_names(self) -> list[str]:
        """Ordered names of the model's output tensors."""
        ...
