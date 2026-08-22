#!/usr/bin/env bash
# Dev launcher — starts the FastAPI backend and the Vite frontend together.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "▶ Backend  : http://127.0.0.1:8010  (docs at /docs)"
echo "▶ Frontend : http://127.0.0.1:5180"
echo

# Backend (stocks venv)
(
  cd "$ROOT/backend"
  ./stocks/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
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
