"""Pure-logic tests for the CV INFRA that stays in the boilerplate.

Models, tracker, matching and the recognition pipeline are scenario-specific
(each scenario builds its own) — they are tested inside each scenario, not here.
The boilerplate only keeps generic infra: model loading (runtime), video
(stream), and the vector store (vectordb).
"""

import numpy as np

from edge.runtime import Manifest, dump_manifest, load_manifest
from edge.stream import LatestFrameBuffer
from edge.vectordb import Hit, QdrantIndex


def test_manifest_roundtrip(tmp_path):
    m = Manifest(family="scrfd", task="detect", weights="w.onnx", input_size=(640, 640))
    dump_manifest(m, tmp_path / "manifest.json")
    loaded = load_manifest(tmp_path / "manifest.json")
    assert loaded.family == "scrfd" and loaded.input_size == (640, 640)


def test_backpressure_keeps_newest():
    buf = LatestFrameBuffer(maxsize=1)
    buf.put(np.zeros((2, 2, 3), np.uint8))
    buf.put(np.ones((2, 2, 3), np.uint8))
    assert buf.get(timeout=0.1).mean() == 1.0


def test_qdrant_constructs_without_connecting():
    # constructing must not import qdrant_client or open a connection
    idx = QdrantIndex(url="http://localhost:6333", collection="c")
    assert idx.collection == "c"
    assert Hit(id="1", score=0.9, payload={}).score == 0.9
