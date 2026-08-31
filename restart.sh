#!/usr/bin/env bash
# Restart launcher — frees the dev ports first, then starts backend + frontend fresh.
# Use this over run.sh when a previous server is still holding a port, or when Vite's
# module cache is stale (e.g. after a mid-edit crash) and needs a clean start.
#
# Windows (Git Bash) notes: the venv lives in backend/stocks/Scripts, and we free
# ports via netstat + PowerShell Stop-Process since pkill can't see the PIDs.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BACK_PORT=8010
FRONT_PORT=5180

free_port() {
  local port="$1"
  # Windows: find the LISTENING PID on the port and kill it.
  local pid
  pid="$(netstat -ano 2>/dev/null | grep ":$port " | grep -i LISTENING | awk '{print $NF}' | head -1)"
  if [ -n "${pid:-}" ]; then
    echo "  freeing port $port (PID $pid)"
    powershell -Command "Stop-Process -Id $pid -Force" 2>/dev/null || true
  fi
  # POSIX fallback (no-op on Windows if lsof is absent).
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$port" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  fi
}

echo "▶ Freeing ports…"
free_port "$BACK_PORT"
free_port "$FRONT_PORT"
sleep 1

# Pick the venv's uvicorn: Scripts on Windows, bin elsewhere.
if [ -x "$ROOT/backend/stocks/Scripts/uvicorn.exe" ]; then
  UVICORN="$ROOT/backend/stocks/Scripts/uvicorn.exe"
elif [ -x "$ROOT/backend/stocks/bin/uvicorn" ]; then
  UVICORN="$ROOT/backend/stocks/bin/uvicorn"
else
  UVICORN="uvicorn"  # fall back to PATH
fi

echo "▶ Backend  : http://127.0.0.1:$BACK_PORT  (docs at /docs)"
echo "▶ Frontend : http://127.0.0.1:$FRONT_PORT"
echo

( cd "$ROOT/backend" && "$UVICORN" app.main:app --host 127.0.0.1 --port "$BACK_PORT" --reload ) &
BACK=$!

( cd "$ROOT/frontend" && npm run dev ) &
FRONT=$!

trap "kill $BACK $FRONT 2>/dev/null || true" EXIT
wait
