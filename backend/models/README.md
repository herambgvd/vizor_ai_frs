# FRS face models

Two model dirs, each with a `manifest.json` + weights:

- `scrfd/scrfd.onnx`  — SCRFD face detector (5 landmarks)
- `embed/embed.onnx`  — 512-d face embedder. `family` in the manifest is `arcface`
  (from InsightFace buffalo_l `w600k_r50.onnx`) by default. To use **AdaFace**,
  drop your exported `adaface.onnx` in as `embed/embed.onnx` and set
  `"family": "adaface"` in `embed/manifest.json` (preprocessing is identical —
  aligned 112×112, (x-127.5)/127.5).

Fetch the default (SCRFD + ArcFace) weights:  `python tools/fetch_models.py`
