"""Fetch the default FRS face models (SCRFD detector + 512-d embedder).

Downloads InsightFace's ``buffalo_l`` pack and extracts the two ONNX files we need:

  * ``det_10g.onnx``   (SCRFD face detector)   -> models/scrfd/scrfd.onnx
  * ``w600k_r50.onnx`` (ArcFace 512-d embedder) -> models/embed/embed.onnx

Both are CPU-capable ONNX models. To use AdaFace instead, replace
``models/embed/embed.onnx`` with your exported adaface.onnx and set
``"family": "adaface"`` in ``models/embed/manifest.json``.

Run from ``frs/backend``:  python tools/fetch_models.py
Stdlib only — no extra deps.
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

URL = "https://github.com/deepinsight/insightface/releases/download/v0.7/buffalo_l.zip"
HERE = Path(__file__).resolve().parent.parent  # frs/backend
DEST = {
    "det_10g.onnx": HERE / "models" / "scrfd" / "scrfd.onnx",
    "w600k_r50.onnx": HERE / "models" / "embed" / "embed.onnx",
}


def main() -> int:
    if all(p.exists() for p in DEST.values()):
        print("models already present:", *[str(p) for p in DEST.values()], sep="\n  ")
        return 0
    print(f"downloading {URL} …")
    try:
        with urllib.request.urlopen(URL, timeout=120) as resp:  # noqa: S310
            data = resp.read()
    except Exception as exc:  # pragma: no cover - network dependent
        print(f"ERROR: download failed: {exc}", file=sys.stderr)
        print("Manually place scrfd.onnx + embed.onnx per models/README.md", file=sys.stderr)
        return 1

    got = 0
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for member in zf.namelist():
            base = Path(member).name
            if base in DEST:
                dest = DEST[base]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(zf.read(member))
                print(f"  extracted {base} -> {dest}")
                got += 1
    if got < len(DEST):
        print("WARNING: not all expected files were found in the archive", file=sys.stderr)
        return 1
    print("done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
