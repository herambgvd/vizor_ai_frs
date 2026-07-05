# Running the FRS stack on a GPU machine

The stack runs on **CPU by default** and on **NVIDIA GPU** with one extra compose
file. Inference (SCRFD detect + face embed) uses the ONNX Runtime CUDA execution
provider — the *same* `.onnx` weights, no re-export.

## 1. Host prerequisites (GPU machine)

- NVIDIA GPU + recent **driver** (CUDA 12.x capable).
- **Docker** + **Docker Compose v2**.
- **NVIDIA Container Toolkit** (lets containers see the GPU):
  ```bash
  # Ubuntu (see NVIDIA docs for other distros)
  sudo apt-get install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  # sanity check:
  docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
  ```

## 2. Get the code + weights

```bash
git clone <this-repo> && cd <repo>/frs/backend
cp .env.example .env                 # then edit secrets
python3 tools/fetch_models.py        # downloads SCRFD + ArcFace ONNX into models/
```
Model weights are **not** committed to git (too large) — `fetch_models.py` fetches
them. To use **AdaFace**, drop your `adaface.onnx` in as `models/embed/embed.onnx`
and set `"family": "adaface"` in `models/embed/manifest.json`.

## 3. Bring it up on GPU

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```
This rebuilds **backend / worker / streams** from `Dockerfile.gpu` (CUDA 12.4 +
cuDNN 9 + `onnxruntime-gpu`), reserves the GPU for them, and sets
`VE_INFERENCE_DEVICE=cuda`.

**Verify GPU inference is active:**
```bash
curl -s localhost:8000/api/v1/recognition/status -H "Authorization: Bearer <token>"
# → {"available":true,"device":"cuda", ...}
docker compose logs backend | grep "face engine loaded"   # device=cuda
```
The Dashboard's GPU tile also lights up (host GPU via nvidia-ml-py).

## 4. CPU vs GPU cheatsheet

| | CPU (default) | GPU |
|---|---|---|
| Up | `docker compose up -d --build` | `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build` |
| Image | `Dockerfile` (onnxruntime) | `Dockerfile.gpu` (onnxruntime-gpu, CUDA) |
| `VE_INFERENCE_DEVICE` | `cpu` | `cuda` (set by the override) |

## 5. Notes

- **Graceful fallback:** the CUDA provider falls back to CPU if the GPU isn't
  visible, so a misconfigured host degrades instead of crashing.
- **Phase 2 — TensorRT / DeepStream:** for max multi-camera throughput, the runtime
  already supports a `tensorrt` manifest backend (engine build) and the design has a
  DeepStream path. onnxruntime-gpu (this setup) is the pragmatic first GPU step and
  needs no engine build.
- **Data:** Postgres/Qdrant/storage volumes are named docker volumes — they persist
  across `up`/`down`. Copy `.env` separately (it's gitignored).
