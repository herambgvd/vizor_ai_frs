#!/usr/bin/env bash
# Re-vendor the shared platform into this repo. Point PLATFORM_SRC at vizor_ai_platform/platform.
set -euo pipefail
SRC="${PLATFORM_SRC:-../vizor_ai_platform/platform}"
[ -d "$SRC/edge" ] || { echo "platform source not found at: $SRC (set PLATFORM_SRC)"; exit 1; }
rsync -a --delete --exclude '.venv' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'web/node_modules' --exclude '.next' "$SRC/" ./platform/
echo "done. rebuild: docker compose up -d --build"
