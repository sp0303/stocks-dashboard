# v2 Post-Reset Plan — Migration reconciliation + Missing frontend features

_Written 2026-09-23. Persistent across context resets. Read this first on "Resume"._

This doc answers two things the owner asked for:
1. **Auto-migrate everything** after reset — what is actually migrated vs. what is not, and how to finish it.
2. **A note of missing frontend features, especially the Manager view** — what data exists in Postgres but is not shown, and what v1 UI has no v2 equivalent.

> **Headline finding:** the migration is far more complete than it looks from the app. Almost all v1 data **is** in Postgres. What the owner perceives as *"watchlists etc. are not migrated"* is mostly a **frontend surfacing gap** — the rows exist, but there is no Manager-view UI rendering them. Only three small data gaps remain (below), plus the ORB subsystem (deferred by the owner to "tomorrow").

---

## 1. Migration reconciliation (count-level, verified live 2026-09-23)

Counts only — no client PII/strategy content read, per AGENTS.md §9. Source: v1 Mongo (`stocks`) vs v2 Postgres on the OCI box.

| v1 Mongo collection | v1 | v2 Postgres table | v2 | Verdict |
|---|---:|---|---:|---|
| managers | 3 | core.managers | 3 | ✅ full |
| clients | 16 | core.clients | 16 | ✅ full |
| trades | 8973 | ledger.trades | 8973 | ✅ full |
| uploads | 35 | ledger.uploads | 35 | ✅ full |
| corporate_actions | 519 | ledger.corporate_actions | 519 | ✅ full |
| dividends | 0 | ledger.dividends | 0 | ✅ (both empty) |
| benchmark_prices | 5693 | market.benchmark_values | 5693 | ✅ full |
| watchlists (docs) | 4 | research.watchlists | 3 | ✅ see note A |
| watchlists (nested entries) | 45 | research.watchlist_entries | 45 | ✅ full — **all entries migrated** |
| boards (nested items) | 1 | research.board_items | 1 | ✅ full — v1 board had only 1 card |
| tags | 0 | research.tags | 0 | ✅ |
| thesis | 2 | research.stock_theses | 2 | ✅ full |
| trade_notes | 2 | research.trade_notes | 1 | ⚠️ **1 lost** — note B |
| trade_tags | 1 | research.trade_tags | 0 | ❌ **not migrated** — note B |
| pdf_uploads | 3 | (none) | 0 | ❌ **not migrated** — note C |
| screener_snapshots | 7 | research.screener_snapshots | 6 | ⏸️ ORB-adjacent, deferred |
| orb_* (candles_1m 109416, candles_1d 2699, calendar, health, jobs, signals, universe, backfill) | many | market.candles_1m etc. | — | ⏸️ **ORB — deferred to "tomorrow" by owner** |

- **Note A (watchlists 4→3):** all 45 entries migrated intact. The 4th Mongo doc collapsed (empty/duplicate/no-entry watchlist). No entry data lost. Treat as ✅ unless the owner names a specific missing list.
- **Note B (trade_tags 1→0, trade_notes 2→1):** almost certainly an ETL **FK-resolution miss** — the tagged/noted trade's fingerprint didn't resolve to a `trade_id` at migration time, so the row was skipped. 3 rows total. Fix = re-run just those two migration steps with corrected fingerprint matching.
- **Note C (pdf_uploads 3):** a **separate** collection from `uploads` (which is the 35 CSV/xlsx tradebooks, fully migrated). PDF tradebook uploads were never in the ETL. Decide: migrate the 3 raw PDFs into `ledger.uploads` (source=pdf) or leave them (they are already parsed into `trades`).

### Auto-migration on resume — what to actually run
The ETL script is at `scratchpad/migrate_mongo_to_pg.py` (deployed to box `/tmp`). A full re-run is **idempotent** (upserts on legacy_id / fingerprint). Steps:
1. **Do NOT re-run during market hours** if it touches the running API — it doesn't restart pi-api, but hold ORB-related steps regardless.
2. Re-run `trade_tags()` + `trade_notes()` **after** the fingerprint→trade_id map is rebuilt, and log which rows still fail to resolve (surface the fingerprint, not the trade content).
3. Decide pdf_uploads (owner call).
4. ORB migration: **tomorrow**, explicitly, per owner. `orb_candles_1m` is 109k rows — check `df -h` first (§10, disk ~75%).

---

## 2. Missing frontend features — the real gap

The data is in Postgres; the v2 React app just doesn't render most of it. v2 today = one 3-tab shell (Portfolios · Watchlists · Board) + client drill-in + super-admin portal (built) + login.

### 2a. MANAGER view — **deepest gap** (owner: "I find many features missing")
v1 manager had: Overview (client list + **aggregated** Holdings/Metrics/Trade-Log), ★ Watchlist, R&D (Sectors), MyBoard, Screener, Corporate Actions.

| v1 Manager feature | v1 component | v2 status | Data in PG? |
|---|---|---|---|
| Client list (Portfolios) | ManagerView | ✅ `ManagerBook.tsx` | yes |
| Aggregated **Holdings** (all clients) | `ManagerHoldings.jsx` | ⚠️ `ManagerHoldingsTable.tsx` exists — verify it aggregates, not per-client | yes (positions_latest / portfolio.*) |
| Aggregated **Metrics** (book-level) | `ManagerMetrics.jsx` | ❌ missing | yes (portfolio.manager_daily / manager_metrics) |
| **Trade Log** across all clients | `ManagerTradeLog.jsx` | ❌ missing | yes (ledger.trades) |
| **Watchlist** (manager's) | `Watchlist.jsx` | ✅ `WatchlistPage.tsx` | yes (3 lists, 45 entries) |
| **MyBoard** Kanban | `MyBoard.jsx` | ✅ `BoardPage.tsx` | yes (1 item) |
| **R&D / Sector Research** | `SectorResearch.jsx` | ❌ missing | needs ORB rollup |
| **Screener** (top-N, sector-wise) | `Screener.jsx` | ❌ missing (v1 `/api/screener` works — see §3) | ORB-fed |
| **Corporate Actions** view | `CorporateActions.jsx` | ❌ missing | yes (519 rows) |
| Per-manager client **scoping** | — | ✅ **fixed + deployed** (was: saw all 16) | — |

**Manager build priority:** Metrics → Trade Log → Corporate Actions (all data already in PG, pure surfacing) come before Sectors/Screener (need ORB).

### 2b. CLIENT view (`ClientView` vs v1 `ClientDashboard`) — core only
Present: Capital Deployed (R1), Market Value, Open Value, Total P&L, Return on Capital, Volatility, Sharpe, Max Drawdown, TWR NAV chart, holdings table.

Missing (data mostly in PG): **P&L Calendar** heatmap (`PnlCalendar.jsx`), **Trade log + tags + journal notes**, **Dividends**, **per-client Corporate Actions**, **Stock detail drawer/analysis** (`StockDetailDrawer`, `StockAnalysis`), **Benchmark comparison** chart (index-units, R10; benchmark_values migrated), **XIRR** display (computed in core, not shown), **manual trade entry / view-delete trades** (only upload modal exists), **authenticated CSV download** (R14).

### 2c. Cross-cutting not in v2
Broker account management (`AccountManager`/`AccountSelector` — deferred, no brokers), live-price/broker status pill, design-system polish (tokens/dark mode/virtualization/4-state), generated API types (`gen:api`).

---

## 3. Screener API (v1) — working, needs top-N / sector params
`GET https://sarey.tech/api/screener` is **live** (v1 backend). Returns all 490 stocks across 20 sectors, snapshot-cached (~1.5s), each with `rank`, composite `score`, momentum (d1/w1/m1/y1), rsi, from_52w_high, rel_strength, fundamentals, value/quality scores.

**Gap:** no `top` / `sector` / `sort` query params — client must slice. Planned (backward-compatible, deploy after 15:30 IST):
- `?top=20` / `?top=50`, `?sector=Healthcare`, `?sort=score|m1|rel_strength`.
- Router: `backend/app/routers/screener.py` `@router.get("")` → add optional query params, slice the cached snapshot before returning. **No ORB restart** needed for the code change, but any `pm2 restart backend` kills the ORB feed for the day (§10) — deploy after market close only.

---

## 4. Suggested overall build order
1. **Finish migration**: re-run trade_tags + trade_notes (fingerprint fix); decide pdf_uploads.
2. **Manager surfacing** (data already in PG): Metrics, Trade Log, Corporate Actions.
3. **Client depth**: benchmark chart, trade log + journal/tags, P&L calendar, XIRR, dividends, stock drill-in, authenticated download.
4. **Screener API params** + a v2 Screener/Sectors page (ties to ORB rollup).
5. **ORB migration** (candles/calendar/signals) — its own day, disk check first.

## Standing cleanups (carried forward)
- Change super-admin password (it was weak); fix the junk "test 1" manager email.
- Wire Yahoo quote provider (poller is a stub → market_value doesn't reflect live prices).
- Commit v2 to `feat/v2-platform` branch; add missing deps to `pyproject.toml`; move §13 hardcoded secrets to env; JWT RS256 (§9).
