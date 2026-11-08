# Portfolio Intelligence v2 — Execution Tracker

**Status:** In Progress · Phase 1 & Critical Path Active
**Last Updated:** 2026-09-22
**Architecture:** Modular Monolith (`pi_api` :8200) + Workers (:8201–:8206) + Pure Domain Core (`pi_core`)

---

## 1. Phase Status Overview

| Phase | Description | Status | Exit Gate Condition |
|---|---|---|---|
| **Phase 0** | Stabilize & Baseline | 🟡 In Progress | Golden fixtures extracted; v1 fixes isolated |
| **Phase 1** | Foundations & `pi_core` | 🟢 ~80% Done | Domain math pure & unit-tested; Alembic baselined |
| **Phase 2** | Data Tier & Ingestion | 🟡 Next | Mongo -> Postgres ETL verified; securities master |
| **Phase 3** | Compute & Read API | 🟡 Next | `portfolio-worker` precomputes `portfolio.*`; shadow verification |
| **Phase 4** | Frontend v2 (`apps/web`) | 🟡 Prototype Done | React 19 + Vite + Tailwind + ECharts running |
| **Phase 5** | Research & ORB | ⚪ Scheduled | Standalone `orb-feed` process (:8205) shadow tested |
| **Phase 6** | Soak, Cutover, Decommission | ⚪ Scheduled | Zero unexplained delta > ₹1; flip nginx |

---

## 2. Critical Path Burn-down Checklist

- [x] **Monorepo Scaffolding (ADR-0001):** `apps/{api,workers,web}`, `libs/pi_core`, `migrations`, `infra`
- [x] **`pi_core` Math Engine (Rules R1–R18):**
  - [x] Single-pass FIFO engine (`engine/fifo.py`)
  - [x] Corporate actions split/bonus multiplier (`engine/corporate_actions.py`)
  - [x] Unmatched sell protection (`engine/matching.py`)
  - [x] Segment separation (`engine/segments.py`)
  - [x] TWR daily NAV series (`series/twr.py`)
  - [x] Benchmark PME index units (`series/benchmark.py`)
  - [x] Capital metrics & return on capital (`metrics/capital.py`)
  - [x] CAGR suppression < 365 days (`metrics/returns.py`)
  - [x] Volatility & Sharpe ratio from daily excess returns (`metrics/risk.py`)
  - [x] Peak-to-trough Drawdown calculation (`metrics/drawdown.py`)
  - [x] XIRR Newton-Raphson + bisection (`metrics/xirr.py`)
  - [x] LTTB downsampling for charts (`series/downsample.py`)
- [x] **Alembic Baseline (Rule 15):**
  - [x] Multi-schema `migrations/env.py` and `alembic.ini`
  - [x] Revision `0001_initial_schema` stamped on `portfolio` database
- [ ] **Redis Events & Cache Layer:**
  - [ ] `core.cache.cached_bytes` with versioned keys
  - [ ] `core.events` Redis Streams publisher/consumer
- [ ] **Worker Implementation (`apps/workers`):**
  - [ ] `portfolio-worker` (:8202) listening on Redis Streams
  - [ ] `ingest-worker` (:8204) broker tradebook parser & ingestion
  - [ ] `quote-poller` (:8201) batch-poll to Redis `q:{exch}:{sym}`
  - [ ] `eod-worker` (:8203) EOD prices & corporate actions
  - [ ] `orb-feed` (:8205) standalone live feed
  - [ ] `scheduler` (:8206) cron triggers with Redis leader lock
- [ ] **Real Data Migration (ETL):**
  - [ ] Export script from Mongo to `core.clients` & `ledger.trades`
  - [ ] Run verification report on counts, hashes, sums
- [ ] **Shadow Verification (Phase 3.4):**
  - [ ] Run `portfolio-worker` over real books (e.g. 4,219-trade client)
  - [ ] Compare v2 output vs v1 output with 0 unexplained deltas > ₹1
- [ ] **Production Infrastructure Configs (`infra/`):**
  - [ ] Systemd unit files for all 7 services
  - [ ] Nginx v2 reverse-proxy configuration
