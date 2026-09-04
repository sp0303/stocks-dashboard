#!/usr/bin/env bash
# Dev launcher — starts the FastAPI backend and the Vite frontend together.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ Backend  : http://127.0.0.1:8010  (docs at /docs)"
echo "▶ Frontend : http://127.0.0.1:5180"
echo

# Backend (.venv — Scripts on Windows, bin elsewhere)
(
  cd "$ROOT/backend"
  if [ -x "./.venv/Scripts/uvicorn.exe" ]; then UV="./.venv/Scripts/uvicorn.exe"; else UV="./.venv/bin/uvicorn"; fi
  "$UV" app.main:app --host 127.0.0.1 --port 8010 --reload
) &
BACK=$!

# Frontend
(
  cd "$ROOT/frontend"
  npm run dev
) &
FRONT=$!

trap "kill $BACK $FRONT 2>/dev/null || true" EXIT
wait
