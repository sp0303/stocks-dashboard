# Portfolio Intelligence Platform

Multi-tenant portfolio analytics for portfolio managers. Upload Zerodha equity tradebooks,
get live-priced holdings, P&L (FIFO), sector/asset allocation, concentration, performance,
and per-stock analysis. **No authentication in Phase 1.**

- **Frontend** — React + Vite (`/frontend`)
- **Backend** — FastAPI (`/backend`), Python venv named **`stocks`**
- **Database** — MongoDB when `MONGODB_URL` is set; otherwise a JSON-file fallback store
  so everything runs with no DB. Paste the Mongo URL into `backend/.env` to switch — no code change.
- **Market data** — Yahoo Finance (direct chart API) behind a provider interface.

See [`docs/`](docs/) for the full HLD/LLD, and the visual blueprint artifact.

## Run locally

Backend (uses the `stocks` venv already created):

```bash
cd backend
./stocks/bin/uvicorn app.main:app --reload --port 8010
```

Frontend (in another terminal):

```bash
cd frontend
npm install   # first time only
npm run dev
```

Or both at once:

```bash
./run.sh
```

Open http://127.0.0.1:5180. The app seeds 2 managers + 3 clients (two mapped to the
sample tradebooks `QPJ806` and `AP8774`). Switch **Super Admin / Manager** at the top-right,
open a client, and upload their `.xlsx` tradebook from the dashboard.

## Configuration — `backend/.env`

```ini
MONGODB_URL=                 # empty = JSON-file store; paste Mongo URL to use MongoDB
MONGODB_DB=stocks
QUOTE_CACHE_TTL_SECONDS=900
CORS_ORIGINS=*
```

## Tests

```bash
cd backend
./stocks/bin/python -m pytest -q
```

Covers the FIFO engine, real-tradebook parsing, and upload dedupe.

## Deploy (later)

- **Frontend → GitHub Pages**: `cd frontend && VITE_API_BASE=https://api.yourdomain.com npm run build`,
  publish `dist/` via GitHub Actions.
- **Backend → public URL via Cloudflare Tunnel**: see [`infra/cloudflared/config.yml`](infra/cloudflared/config.yml).

## Project layout

```
backend/    FastAPI app, stocks venv, tests
  app/services/engine.py       pure FIFO engine (unit-tested, DB-free)
  app/services/ingestion.py    Zerodha .xlsx parser
  app/services/market_data.py  Yahoo quotes (provider interface)
  app/services/analytics.py    holdings, allocation, concentration, performance
  app/store.py                 Mongo + JSON-file backends (same API)
frontend/   React + Vite dashboard (Super Admin + Manager)
docs/       HLD/LLD specification
infra/      Cloudflare tunnel config
```
