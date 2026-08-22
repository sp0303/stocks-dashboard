# Portfolio Intelligence Platform — Design Specification

Planning-phase spec. **No application code yet.** These documents define the HLD and LLD
before implementation begins.

## Decisions locked (2026-08-22)

| Area          | Decision                                                            |
| ------------- | ------------------------------------------------------------------- |
| Frontend      | React, published to GitHub Pages via GitHub Actions                 |
| Backend       | Python + FastAPI, deployed on Azure Functions                       |
| Database      | **MongoDB only** (Phase 1). Mongo for news/AI added in Phase 2.     |
| Tradebook     | Zerodha-style broker export (Excel/CSV, known columns)              |
| Cost basis    | FIFO, **including** transaction costs (brokerage/taxes/charges)     |
| Market data   | yfinance behind a `MarketDataProvider` interface (Kite later)       |
| Client login  | None in Phase 1 (read-only client login is Phase 4)                 |

## Core principles

1. **Trades are the source of transaction truth.** Everything else is derived.
2. **Holdings and P&L are computed**, never stored as hand-entered input.
3. **Ownership is enforced in the backend**, never trusted from the frontend.
4. **Uploads are versioned and deduped** — re-uploading a wider date range never doubles P&L.
5. **Market data enriches, it does not define ownership.** yfinance down ≠ portfolio gone.

## Documents

| Doc                                              | Contents                                           |
| ------------------------------------------------ | -------------------------------------------------- |
| [01-hld.md](01-hld.md)                           | System context, components, deployment topology    |
| [02-data-model.md](02-data-model.md)             | MongoDB collections, indexes, relationships        |
| [03-api-contracts.md](03-api-contracts.md)       | REST endpoints, auth, RBAC                          |
| [04-ingestion-and-engine.md](04-ingestion-and-engine.md) | Upload pipeline + FIFO calculation engine  |
| [05-project-structure.md](05-project-structure.md) | Frontend + backend folder layout                 |

## Mongo-only: what we give up and how we compensate

| Lost vs Postgres            | Compensation in FastAPI layer                                  |
| --------------------------- | ------------------------------------------------------------- |
| FK constraints              | App-layer ownership checks on every request                   |
| Cross-collection joins      | Denormalize read paths + `$lookup` where cheap                |
| Schema enforcement          | Pydantic models validate at the boundary                      |
| Unique-row integrity        | Compound **unique indexes** (trade fingerprint) for dedupe    |
| Multi-row transactions      | Mongo multi-doc transactions (replica set) for upload commit  |
