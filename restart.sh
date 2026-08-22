#!/usr/bin/env bash
# Restart script — kills existing processes and starts backend, frontend, and tunnel
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🛑 Stopping any existing processes on ports 8010 and 5180, and any running cloudflared..."
fuser -k 8010/tcp 2>/dev/null || true
fuser -k 5180/tcp 2>/dev/null || true
pkill cloudflared 2>/dev/null || true
sleep 1

echo "▶ Backend  : http://127.0.0.1:8010"
echo "▶ Frontend : http://127.0.0.1:5180"
echo "▶ Tunnel   : Starting..."
echo

# Backend
(
  cd "$ROOT/backend"
  if [ -f "stocks/bin/uvicorn" ]; then
    ./stocks/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
  else
    uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
  fi
) &
BACK=$!

# Frontend
(
  cd "$ROOT/frontend"
  npm run dev
) &
FRONT=$!

# Cloudflare Tunnel
(
  # Using the tunnel name from your bash history
  cloudflared tunnel run trading-tunnel
) &
TUNNEL=$!

trap "echo -e '\nStopping all services...'; kill $BACK $FRONT $TUNNEL 2>/dev/null || true" EXIT
wait
