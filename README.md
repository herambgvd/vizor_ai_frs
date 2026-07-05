# Vizor AI — FRS (Face Recognition)

Standalone scenario app. FastAPI backend on the vendored **edge** platform +
DashCode Next.js frontend. Full FRS suite: POI/Groups, Cameras, Live (VMS wall),
Events, Investigate, Transit, Tour, Reports, Recognition Settings, Ingest API, TTS,
public dashboard.

## Run (dev)
```bash
cp .env.example .env
docker compose up -d --build
```
Frontend http://localhost:3000 · Backend http://localhost:8000/api/v1 ·
Login support@geniusvision.in / Gvd@6001

Live recognition worker (needs real RTSP cameras): `docker compose --profile live up -d streams`

## Update the vendored platform
```bash
PLATFORM_SRC=../vizor_ai_platform/platform ./sync-platform.sh
```
