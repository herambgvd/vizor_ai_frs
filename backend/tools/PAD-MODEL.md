# Liveness / Presentation-Attack Detection (PAD) model

The anti-spoof control (STQC / ISO-IEC 30107) is framework-complete and off by
default. To activate it, enable the config flags and drop a PAD ONNX model into
`models/pad/`. No code changes are needed — the model is loaded lazily and driven
by its `manifest.json`, exactly like the SCRFD detector and the embedder.

## 1. Enable the policy

In `.env`:

```bash
VE_PAD_ENABLED=true
VE_PAD_THRESHOLD=0.5              # reject liveness < 0.5 as a spoof
VE_PAD_BLOCK_WHEN_UNAVAILABLE=false   # true = fail closed if no model present
```

With `pad_enabled=true` but **no** model present, enrolment stays allowed and logs
a warning (fail-open) unless `pad_block_when_unavailable=true`.

## 2. Drop in a model

Recommended: the **Silent-Face / MiniFASNet** family (minivision), which is small,
CPU-friendly, and widely used for RGB face anti-spoofing. Convert its PyTorch
weights to ONNX (`torch.onnx.export`, opset 11+) and place the file at
`models/pad/pad.onnx` with a manifest:

```json
// models/pad/manifest.json
{
  "family": "minifasnet",
  "task": "liveness",
  "weights": "pad.onnx",
  "input_size": [80, 80],
  "backend": "onnx",
  "preprocess": { "swap_rb": true, "scale": 0.00392156862 },
  "postprocess": { "softmax": true, "live_index": -1, "crop_margin": 0.0 }
}
```

Tune to your model:

| Field | Meaning |
|---|---|
| `input_size` | model input `[w, h]` (MiniFASNet: `[80, 80]`) |
| `preprocess.scale` | pixel scale (`1/255` here; use `1.0` if the model expects 0–255) |
| `preprocess.swap_rb` | BGR→RGB (true for most torch models) |
| `postprocess.softmax` | apply softmax to logits before reading the live prob |
| `postprocess.live_index` | index of the "real/live" class in the output vector |
| `postprocess.crop_margin` | expand the face box by this fraction before scoring (spoof cues live in the surroundings — screen bezel, paper edge) |

## 3. Verify

```bash
curl -s $API/api/v1/recognition/status -H "Authorization: Bearer $T" | jq
# → { ..., "pad_enabled": true, "pad_available": true, "pad_threshold": 0.5 }
```

Then enrol a printed photo of a face — the response should be
`{"enrolled": false, "reason": "spoof_detected", "liveness": <low>}`. A live
capture enrols normally and carries a `"liveness"` score.

## Notes

- PAD runs on the same ONNX runtime + device (`VE_INFERENCE_DEVICE`) as the other
  face models — CPU by default, CUDA when available.
- The check is enforced at **enrolment** today; the same `FaceEngine.liveness()`
  hook is available to the live recognition pipeline for per-appearance scoring.
- For a formal ISO 30107-3 PAD evaluation (APCER/BPCER), test against a labelled
  attack dataset; this control provides the enforcement mechanism, not the
  certification test itself.
