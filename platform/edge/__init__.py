"""edge — reusable INFRA for single-tenant CV scenario apps.

The boilerplate holds only scenario-AGNOSTIC infrastructure. Anything that differs
per AI scenario — the model adapters, the tracker, the recognition pipeline, the
matching strategy, the domain — is built INSIDE each scenario (scenarios/frs,
scenarios/anpr, ...), NOT here.

Layout (what each package owns):
  core/      config, licensing, feature-module registry, FastAPI factory, errors,
             logging, pagination, ratelimit, metrics, secrets, storage, limits,
             ws_auth, realtime, health
  auth/      users, JWT, dynamic RBAC (roles + permissions), API keys
  licensing/ license status + runtime renewal
  branding/  white-label logo + theme
  messaging/ email + FCM push + webhook + in-app + templates + dispatcher
  tasks/     Celery app + beat + retention cleanup
  reports/   CSV / XLSX / PDF export framework
  system/    CPU/RAM/GPU/disk resources
  db/        async SQLAlchemy base + TimescaleDB helpers
  runtime/   model LOADING (ONNX / OpenVINO / TensorRT) behind one interface  ← generic driver
  stream/    RTSP ingest (FFmpeg) + MediaMTX + overlay + backpressure          ← video plumbing
  vectordb/  Qdrant client wrapper (optional)                                  ← DB client
  hooks.py   ScenarioHook — the seam where a scenario plugs its per-frame logic in

NOT here (each scenario builds its own): models (SCRFD/AdaFace vs plate+OCR),
tracker, recognition pipeline, matching, appearance/events, domain.

A scenario app imports this package for infra, then writes its own models +
recognizer hook + domain + feature modules, and calls core.create_app().
"""

__version__ = "0.1.0"
