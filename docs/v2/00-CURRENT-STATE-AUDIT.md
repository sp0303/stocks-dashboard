# v2 — Current-State Audit (the evidence behind the plan)

**Status:** draft for approval · 21 Sep 2026
**Scope:** `stocks-dashboard` (v1) as it runs today. Everything here was **measured or read from the code**, not assumed. Where something could not be verified it says so.
**How measured:** a restored copy of the production Mongo dump (16 clients, 8,925 trades, 2020-11 → 2026-09) served by the v1 backend on a dev Mac, timed from the logged-in browser.

> **Read this caveat.** The backend that served these requests was v1's `main` **working tree, which already contains the (uncommitted, undeployed) metric fixes**, including the daily-calendar series. That fix makes the performance payload larger and the series computation heavier than the code deployed today (which emitted one point per *trade day*: 15 points for a 102-trade client instead of 143). So the **payload sizes and the `/performance` timings below overstate today's production**. The cold-vs-warm *shape* and the provider-bound timings (`/portfolio`, `/holdings`, manager `/metrics`) do not depend on that fix. Absolute numbers will also differ on the OCI VM. Phase 0.6 re-measures deployed v1 on the real box.

---

## 1. Headline

> v1 is **fast when warm and slow when cold**. Warm calls take 1–70 ms; cold calls take 0.9–7 s. The speed comes entirely from per-process Python dictionaries, so it disappears on every restart, every TTL expiry and (if more than one worker runs) on every other worker.

Adding Redis alone would not fix this. The cold path itself is expensive, because it computes and calls out to brokers on the request path.

## 2. Measured latency

| Endpoint | 1st call (cold) | 2nd call (warm) | Payload |
|---|---:|---:|---:|
| Client (4,219 trades) `/portfolio` | **7,048 ms** | 32 ms | 1 KB |
| Client (4,219 trades) `/performance` | **2,639 ms** | 35 ms | **483 KB** |
| Client (102 trades) `/performance` | 886 ms | 7 ms | 55 KB |
| Client (102 trades) `/holdings` | **3,872 ms** | 9 ms | 3 KB |
| Manager (11 clients) `/metrics` | 1,220 ms | 61 ms | 3 KB |
| Manager (11 clients) `/performance` | **6,984 ms** | 72 ms | **693 KB** |
| Manager `/trade-log` | 51 ms | 49 ms | 101 KB |

Rows that show ~20 ms on the first call were already warm from earlier browsing. The cold rows are the signal.

**The v2 target is cold = warm**: every read in the table above at p95 ≤ 150 ms with no cache, because the answer is already computed (see HLD D1).

## 3. Root causes

| # | Cause | Evidence |
|---|---|---|
| R1 | **Compute on the request path.** The performance series re-runs the full FIFO engine once per trade-day, so cost grows with trades × days. | `compute_performance_series` → `analytics.daily_performance_series`; the code comment in `routers/portfolio.py` calls it "O(trades²)". |
| R2 | **Broker/provider network I/O on the request path.** Live quotes go Angel One → Yahoo; history is fetched per symbol; index history is fetched per index. Yahoo returned HTTP 429 during testing. | Network calls in `services/angel.py` (18 sites), `securities.py` (9), `market_data.py` (5), plus `routers/portfolio.py` and `analytics.py`. |
| R3 | **Eleven separate in-process caches, TTL-only, no invalidation.** Different TTLs (10 min, 15 min, 30 min, 6 h). Lost on restart. Not shared between workers. | See §4. |
| R4 | **Payload bloat.** One row per calendar day with ~17 keys, as an array of objects, with no downsampling. There is no compression middleware in the app (only CORS). Nginx compression is unverified. | 483 KB / 693 KB above; `main.py` middleware list. |
| R5 | **Repeated work per page.** `build_holdings` (which fetches quotes) is called from portfolio, holdings, allocation, concentration, XIRR, CAGR and risk. `ClientDashboard.jsx` fires 19 independent fetch hooks. | grep of `build_holdings(` in `analytics.py`; `useAsync` count. |
| R6 | **Process model unknown.** The uvicorn worker count and pm2 settings are not in the repo, so whether per-process caches are duplicated is unverified. | `.github/workflows/deploy.yml` is disabled and has no pm2 config. |

## 4. In-process cache inventory (all of these become one Redis design)

| Cache | Where | TTL |
|---|---|---:|
| `_perf_series_cache` | `routers/portfolio.py:211` | 15 min |
| `_ta_cache` (trade analytics) | `routers/portfolio.py:379` | 15 min |
| Screener snapshot | `routers/screener.py:94` | 10 min |
| `QuoteCache` | `services/market_data.py:377` | env, 900 s in the old deploy file |
| `_details_cache` | `services/market_data.py:56` | env |
| `_history_cache` | `services/market_data.py:152` | ≥ 30 min |
| `_price_matrix_cache` | `services/market_data.py:565` | ≥ 30 min |
| `MarketDataCache` | `services/market_data_cache.py:6` | — |
| `SimpleCache` | `cache.py:6` | — |
| News cache | `services/stock_news.py:21` | 30 min |
| Failed-lookup cache | `services/securities.py:29` | 6 h |

(`screener_daily._kpis_cache` is a twelfth, load-once.) The quote cache was keyed by symbol only, so whichever exchange loaded first priced every holding of that symbol. That is a latent correctness bug (fixed on the working tree, not yet deployed); I did not confirm it changed a production number.

## 5. Data volumes (production copy)

| Collection | Docs | Data | Note |
|---|---:|---:|---|
| `orb_candles_1m` | 104,041 | **2.2 GB** | one doc per symbol-day, seven parallel arrays of 375 values; 2024-08 → 2026-09 |
| `orb_candles_1d` | 2,699 | 156 MB | one doc per symbol, multi-year array |
| `trades` | 8,925 | 4 MB | the portfolio core is tiny |
| `benchmark_prices` | 7,128 | 0.6 MB | 4 index series |
| `corporate_actions` | 519 | 0.2 MB | |
| everything else | < 1,000 each | < 1 MB | |

Two conclusions that shape the design:

1. **The portfolio data is small.** A database swap does not, by itself, fix latency. Precompute and a price store do.
2. **Candle storage is the one place scale matters.** ~39 M one-minute bars already, growing ~1 GB/year uncompressed on a VM whose root disk was **75 % full (7.5 GB free)** when last observed. Compressed time-series storage is a real requirement here.

Indexes: 11 in total. `trades` has `(client_id, fingerprint)` unique and nothing on `(client_id, trade_date)`. Every read is a filter on `client_id`, so this is served by the unique index prefix today, but there is no schema, no migrations, and money is stored as floats.

## 6. Code structure

| Fact | Number |
|---|---:|
| HTTP routes | **114** across 13 routers |
| `routers/portfolio.py` | 1,419 lines, 48 routes (routing + compute + caching + I/O in one file) |
| `services/analytics.py` | 1,832 lines (pure math mixed with quote fetching and network classification) |
| `store.py` | 1,524 lines, **206 methods**, three classes (Base / Json / Mongo) |
| Backend test files | 23 committed (27 with the new, uncommitted metric tests). No CI; the deploy workflow is disabled |
| Frontend | 6,811 lines of JSX, no TypeScript, no server-state library |
| `ClientDashboard.jsx` | 1,403 lines, 19 hand-rolled fetch hooks |

## 7. Frontend

Not the bottleneck. Initial JS is **62 KB gzip** (index 58 + common 3), inside quest-mf's 150 KB budget. The Recharts chunk is 101 KB gzip and is loaded lazily. What is missing is structure: no types, no shared cache for server data (each tab refetches), no generated API client, and one 1,400-line file owning a whole product area.

## 8. Operations

| Area | Finding |
|---|---|
| Host | One OCI VM. Root disk 30 GB, 75 % used at last observation. |
| Process supervision | nginx + pm2 (`portfolio-backend`). |
| Deploys | Manual over SSH. GitHub Actions workflow is disabled and points at the retired box. |
| Restart hazard | Restarting the backend between **08:45 and 15:30 IST** breaks the ORB feed subscription for the day, so deploys are calendar-constrained. Root cause: the feed runs inside the API process. |
| Data tier | Mongo on the same VM. quest-mf's CHANGELOG says its Postgres and Redis are reached at `140.245.194.172:5432/6379`, the same host. **Verify whether those ports are reachable from the internet** (quest-mf's own rules forbid it). |
| Observability | Logs only. No metrics, no tracing, no slow-query visibility. |
| Backups | Not verified. |
| Docs | `docs/01–05` still describe Azure Functions + GitHub Pages; they are stale. |

## 9. Correctness debt found in the metrics audit (Sept 2026)

The audit of the metrics found defects in the numbers themselves, not just the speed. They are fixed on the `main` working tree (uncommitted, **not deployed**) and are the source of `DOMAIN-RULES.md`:

| Defect class | Example |
|---|---|
| Two Sharpe functions, the wrong one live | Sharpe was blank for every portfolio |
| Flows counted as performance | v1's series made a full sale read as a ~−90 % day, which fed volatility, drawdown and beta |
| "Invested" = `buy − sell` | Went negative on a profitable recycling book |
| Chart sampled on trade-days only | 15 points across 191 days; 48-day straight lines |
| Benchmark subtracted open cost | Nifty showed ₹0 gain when the client took a profit |
| Cache keyed without exchange | latent: one exchange's price could price another's holding |
| Frozen broker feed served as live | VENUSREM stuck at ₹1,797.50 for three months (13.6 % overstatement) |
| Dead index ticker | Midcap 100 flatlined from 17 Jul 2026 |
| Unmatched sells booked as profit on charts | Demerger credits moved a chart ~60 % in a day |
| Percent units | Volatility shown as 0.14 % instead of 14 % |
| Manager vs client disagreed | Intraday counted on one page and not the other |
| Kite sync wrong endpoints | `positions()` instead of `holdings()`; `orders()` only returns today |

**A lesson from the fix itself (not a v1 defect):** my first draft of the time-weighted return passed all its unit tests and then produced a **−1084 % drawdown** on one real book (a ₹434 residual topped up with ₹3,514 gave a −403 % day and left NAV negative for 746 days). It was found only by running the code on the real dataset. That is why rule R2 defines the capital base carefully, R16 exists, and AGENTS §7 requires verification on production-shaped data.

**Implication:** v2 must be built from these rules and golden fixtures, not by porting v1 code line by line. It also means the `main` fixes should be shipped **before** v2 work starts, so users are not looking at wrong numbers for months (MIGRATION-PLAN Phase 0).

## 10. What v1 does well (keep)

- The pure FIFO engine and its tests (`engine.py`) are sound; the design docs already say it must stay DB-free.
- Same-day netting, ISIN reconciliation across renames, unmatched-sell handling, corporate-action scaling.
- Ingestion fingerprinting that includes the broker trade id (correctly keeps separate fills separate).
- The ORB engine's calendar, session and bar-building logic, which has its own tests.
- Real broker integrations (Angel One market data, Kite).
- The product surface itself: manager book, client dashboard, playbook, sector research, screener, board.
