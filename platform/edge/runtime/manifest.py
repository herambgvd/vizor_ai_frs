"""Model manifest — the little JSON file that describes a servable model.

Every model directory ships a ``manifest.json`` next to its weights. The
manifest is the single source of truth telling the runtime *what* the model is
(family / task), *which* weights file to load, *which* engine to run it on, and
the pre/post-processing knobs the family layer needs. This is what makes the
runtime pluggable: point it at a model dir and it self-describes.

Example ``manifest.json`` for an SCRFD face detector::

    {
      "family": "scrfd",
      "task": "detect",
      "weights": "scrfd_10g.onnx",
      "input_size": [640, 640],
      "backend": "onnx",
      "preprocess": {"mean": 127.5, "std": 128.0},
      "postprocess": {"conf_thresh": 0.5, "nms_thresh": 0.4}
    }
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Allowed vocabularies. Kept as module constants so both validation and any
# caller can reference the same canonical sets.
FAMILIES = ("scrfd", "adaface", "arcface", "yolo", "genderage")
TASKS = ("detect", "embed", "classify")
BACKENDS = ("onnx", "openvino", "tensorrt")


@dataclass(frozen=True)
class Manifest:
    """Immutable description of one servable model.

    Frozen because a manifest is config: once loaded it should not mutate under
    the runtime's feet. Copy-and-replace if you need a variant.
    """

    family: str            # one of FAMILIES — picks the pre/post-processing family
    task: str              # one of TASKS — what the model produces
    weights: str           # weights filename, relative to the model dir
    input_size: tuple[int, int] = (640, 640)  # (width, height) fed to the net
    embed_dim: int | None = None              # embedding length for embed tasks
    backend: str = "onnx"                     # one of BACKENDS — which engine
    preprocess: dict = field(default_factory=dict)   # family-specific knobs
    postprocess: dict = field(default_factory=dict)  # family-specific knobs


def load_manifest(path: str | Path) -> Manifest:
    """Read + validate a ``manifest.json`` from ``path``.

    Args:
        path: path to the manifest JSON file (not the directory).

    Returns:
        A validated, frozen :class:`Manifest`.

    Raises:
        ValueError: if the file is missing, unreadable, not an object, is
            missing a required key (family/task/weights), or carries an
            unknown family/task/backend value.
    """
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"manifest not found: {p}")

    try:
        raw = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise ValueError(f"could not read manifest {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError(f"manifest {p} must be a JSON object, got {type(raw).__name__}")

    # Required keys — the runtime cannot do anything useful without these.
    for key in ("family", "task", "weights"):
        if not raw.get(key):
            raise ValueError(f"manifest {p} missing required field '{key}'")

    family = raw["family"]
    task = raw["task"]
    backend = raw.get("backend", "onnx")

    # Validate against the known vocabularies so typos fail loudly here rather
    # than as a confusing error deep inside a family or engine.
    if family not in FAMILIES:
        raise ValueError(f"manifest {p}: unknown family '{family}' (expected one of {FAMILIES})")
    if task not in TASKS:
        raise ValueError(f"manifest {p}: unknown task '{task}' (expected one of {TASKS})")
    if backend not in BACKENDS:
        raise ValueError(f"manifest {p}: unknown backend '{backend}' (expected one of {BACKENDS})")

    # input_size may arrive as a JSON list; normalize to a 2-tuple of ints.
    input_size = raw.get("input_size", (640, 640))
    try:
        w, h = input_size
        input_size = (int(w), int(h))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"manifest {p}: input_size must be [width, height], got {input_size!r}") from exc

    embed_dim = raw.get("embed_dim")
    if embed_dim is not None:
        embed_dim = int(embed_dim)

    return Manifest(
        family=family,
        task=task,
        weights=raw["weights"],
        input_size=input_size,
        embed_dim=embed_dim,
        backend=backend,
        preprocess=raw.get("preprocess", {}) or {},
        postprocess=raw.get("postprocess", {}) or {},
    )


def dump_manifest(m: Manifest, path: str | Path) -> None:
    """Write ``m`` back out as a pretty ``manifest.json`` at ``path``.

    Helper for tooling/tests that generate model directories. ``input_size`` is
    serialized as a JSON list (tuples aren't a JSON type).
    """
    data = asdict(m)
    data["input_size"] = list(m.input_size)  # tuple -> list for clean JSON
    Path(path).write_text(json.dumps(data, indent=2))
