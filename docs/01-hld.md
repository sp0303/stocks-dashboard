# 01 — High-Level Design

## System context

```
   Super Admin ─┐
   Manager     ─┼─▶ React SPA (GitHub Pages) ──HTTPS/JWT──▶ FastAPI (Azure Functions)
   (Client, P4)─┘                                                │
                                                                 ├─▶ MongoDB (Azure)
                                                                 └─▶ Market Data Service ─▶ yfinance
                                                                                            (Kite later)
```

- Frontend is fully static; all secrets and provider keys live server-side.
- The browser never calls yfinance or Mongo directly. Only the FastAPI API.

## Component map (backend modules)

```
FastAPI app
├── auth            login / refresh / logout, JWT issue+verify
├── rbac            role + ownership guards (dependency-injected)
├── users           super-admin manages managers
├── clients         managers manage their clients
├── tradebooks      upload → validate → import → version history
├── trades          query/filter raw ledger
├── engine          FIFO position + P&L calculation (pure, DB-agnostic)
├── portfolio       holdings, pnl, allocation, performance (reads snapshots)
├── securities      security master (symbol → sector/industry/asset_class)
├── market_data     MarketDataProvider interface + YFinanceProvider + cache
├── watchlists      manager-level and client-level
└── audit           append-only action log
```

The **engine** module is pure Python (takes a list of trades, returns positions +
realized P&L). It has no Mongo dependency, so it is unit-testable in isolation and
reusable when Kite arrives.

## Deployment topology

```
GitHub repo
  ├── /frontend  ──build──▶ GitHub Actions ──▶ GitHub Pages (static SPA)
  └── /backend   ──deploy─▶ Azure Functions (Python, ASGI/FastAPI)
                                   │
                                   ├─▶ Azure Cosmos DB for MongoDB (or Azure Mongo)
                                   └─▶ yfinance (outbound)
```

### Function decomposition (avoid one giant function)

The upload path is split so a slow/failed step doesn't block the request:

```
[HTTP] POST tradebook  →  validate + persist raw file + trades   (sync, fast)
[Queue/Timer] recompute →  FIFO engine → positions → snapshot     (async worker)
[Timer] eod-snapshot    →  daily portfolio_daily_snapshots        (scheduled)
[Timer] quote-refresh   →  refresh market_quotes_cache            (scheduled)
```

Phase 1 can run recompute synchronously after upload; the split above is the target
once volume grows. Design the recompute as a callable job either way.

## Non-functional targets (Phase 1)

- Dashboard reads served from **precomputed snapshots/positions**, not recomputed per request.
- yfinance outages degrade to "cannot value" (last cached price + staleness flag), never "no holdings".
- Every mutating endpoint writes an `audit_logs` entry.
