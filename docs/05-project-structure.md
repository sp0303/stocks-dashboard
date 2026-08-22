# 05 — Project Structure

Monorepo: `/frontend` (React → GitHub Pages) and `/backend` (FastAPI → Azure Functions).

```
stock-dashboard/
├── docs/                          # this spec
├── frontend/
│   ├── src/
│   │   ├── api/                   # typed API client (axios), one module per resource
│   │   ├── auth/                  # JWT storage, refresh, route guards
│   │   ├── components/            # reusable UI (charts, tables, cards)
│   │   ├── features/
│   │   │   ├── admin/             # manager management
│   │   │   ├── clients/           # client list + create
│   │   │   ├── tradebook/         # upload + version history
│   │   │   └── portfolio/         # overview, holdings, allocation,
│   │   │                          #   performance, trades, stock-analysis, watchlist
│   │   ├── lib/                   # money formatting (paise→₹), date utils
│   │   └── routes.tsx
│   ├── .github/workflows/pages.yml
│   └── package.json
│
└── backend/
    ├── app/
    │   ├── main.py                # FastAPI app factory, router registration
    │   ├── config.py              # settings (Mongo URI, JWT secret) from env
    │   ├── db.py                  # Mongo client + index creation on startup
    │   ├── deps.py                # get_current_user, require_role, require_client_access
    │   ├── models/                # Pydantic schemas (request/response/db)
    │   │   ├── user.py  client.py  trade.py  upload.py  position.py
    │   │   ├── security.py  snapshot.py  watchlist.py
    │   ├── routers/
    │   │   ├── auth.py  admin.py  clients.py  tradebooks.py  trades.py
    │   │   ├── portfolio.py  watchlists.py  market.py
    │   ├── services/
    │   │   ├── ingestion/
    │   │   │   ├── parser.py      # xlsx/csv → rows
    │   │   │   ├── mapping.py     # broker column profiles (zerodha.yaml)
    │   │   │   ├── validate.py    # row validation
    │   │   │   └── importer.py    # fingerprint, dedupe insert, upload versioning
    │   │   ├── engine/
    │   │   │   ├── fifo.py        # PURE: trades → positions + realized_pnl
    │   │   │   ├── valuation.py   # positions + quotes → unrealized, value
    │   │   │   ├── allocation.py  # sector/asset/stock/concentration
    │   │   │   └── snapshot.py    # write portfolio_daily_snapshots
    │   │   ├── market_data/
    │   │   │   ├── provider.py    # MarketDataProvider ABC (interface)
    │   │   │   ├── yfinance_provider.py
    │   │   │   └── cache.py       # read/write market_quotes_cache
    │   │   ├── securities.py      # security master lookup/enrich
    │   │   └── audit.py
    │   └── workers/
    │       ├── recompute.py       # engine job (called post-import or via queue)
    │       ├── eod_snapshot.py    # timer-triggered
    │       └── quote_refresh.py   # timer-triggered
    ├── function_app.py            # Azure Functions ASGI entry + timer bindings
    ├── tests/
    │   ├── test_fifo.py           # engine unit tests (no DB) — highest priority
    │   ├── test_dedupe.py
    │   └── test_ownership.py
    ├── requirements.txt
    └── host.json / local.settings.json
```

## Layering rule

```
routers  →  services  →  db
   │           │
   └── deps ───┘ (auth + ownership)
engine/*  = pure, no db, no fastapi  → unit-testable, Kite-reusable
```

Routers never do business logic; services never read the request; the FIFO engine never
touches Mongo. That separation is what makes the Phase-3 Kite swap a `provider.py` change
rather than a rewrite.

## Environment / secrets

| Secret            | Where                                   |
| ----------------- | --------------------------------------- |
| Mongo URI         | Azure Functions app setting             |
| JWT signing key   | Azure Functions app setting             |
| (Phase 3) Kite key| Azure Functions app setting             |

Nothing sensitive ships to GitHub Pages — the frontend only knows the API base URL.
