# Portfolio Intelligence v2 — Audit & Completion Plan

_As of 2026-09-22. Status verified live against the OCI box and the working tree._

Constraint set by owner: **no broker credentials in env for now → Yahoo is the market-data
source** (this also removes the §10 Angel-single-identity conflict, so the broker workers
can stay off). Real client data migration to be **run by the user** per AGENTS.md §9 (agent
builds the script + reconciles counts only).

---

## PART 1 — AUDIT (what is done vs missing)

### A. Infrastructure (server) — ~DONE
| Item | Status |
|---|---|
| Redis cache `6390` (allkeys-lru) + streams `6391` (noeviction, AOF) | ✅ live, boot-enabled, localhost |
| Postgres `portfolio` DB + roles `pi_migrator/pi_api/pi_worker/pi_readonly` | ✅ created, connection-tested |
| `pi` service user + `/var/www/portfolio-v2` | ✅ |
| Python 3.11 venv + deps | ✅ (had to hand-add email-validator, python-multipart, argon2-cffi, python-jose, psycopg2) |
| nginx vhost `v2.sarey.tech` (Cloudflare Flexible, port 80) | ✅ live |
| TimescaleDB | ❌ dropped (no aarch64 build) — using plain PG like quest-mf |

### B. Database — schema DONE, data NOT migrated
| Item | Status |
|---|---|
| 8 schemas + ~40 tables | ✅ applied |
| Alembic baseline stamped on remote (`0001_initial_schema`) | ✅ |
| **Real data migrated from v1 Mongo** | ❌ **NONE** — only synthetic (1 mgr, 2 clients, 8 trades) |
| `orb.*` tables | ❌ **schema empty (0 tables)** |

### C. Backend
| Item | Status |
|---|---|
| `pi_core` (engine: fifo/matching/segments/corp-actions; metrics: capital/returns/risk/drawdown/xirr; series: twr/benchmark/calendar/downsample; analytics) | ✅ ~1800 lines, 35 unit tests pass |
| API modules mounted: `auth, portfolio, ledger, market, research, ops` (32 routes) | ✅ |
| Route protection (`require_manager`) on portfolio/ledger | ✅ (deployed: 401 without token) |
| **6 workers built** (portfolio, ingest, quote-poller, eod, orb-feed, scheduler) | ⚠️ built, **NOT deployed/running** on box |
| **Manager aggregation endpoints** (`/managers/*` rollups) | ❌ table `manager_daily` exists, no endpoints |
| **Admin / client-manager CRUD** (create managers/clients, assign) | ❌ only `POST /auth/users` |
| **Screener** (ranked swing-trade screen) | ❌ table `research.screener_snapshots` exists, no logic/data |
| **ORB engine + endpoints** (signals/journal/feed) | ❌ none |
| **Sectors / R&D** | ❌ none |
| Market data via **Yahoo** (no broker) | ❌ **quote-poller is a stub** — no provider fetch at all (no Yahoo/Angel/httpx); v1's Yahoo provider must be ported. **Nothing fetches live prices in v2 today.** |

### D. Frontend
| Item | Status |
|---|---|
| Login page, auth store (token in memory), silent refresh | ✅ |
| Portfolio: ManagerBook + ClientView + metric cards + ECharts | ✅ |
| Tradebook upload modal | ✅ |
| Watchlists + Kanban board pages | ✅ |
| Design tokens / DESIGN.md, virtualization, 4-states everywhere, `gen:api` types | ❌ polish pending |
| Screener / ORB / sectors / manager-admin UI | ❌ none |

### E. Auth / security
| Item | Status |
|---|---|
| argon2id hashing, JWT + refresh, route protection | ✅ |
| **RS256** (ADR-0006 requires it) | ❌ currently **HS256** |
| Admin login | ⚠️ weak password at the time of the audit — **must change** (rotate with `scripts/reset_user_passwords.py`) |
| §13 hardcoded secrets (`settings.py` pi_api pw, `alembic.ini` pi_migrator pw) | ❌ move to env + rotate |

### F. Deployment / ops
| Item | Status |
|---|---|
| `pi-api` systemd service live (`:8200`) | ✅ |
| 6 worker systemd units | ⚠️ files on box, **not installed/started** |
| v2 in git | ❌ rsync only — not committed to any branch |
| Missing deps added to `pyproject.toml` | ❌ hand-installed, not codified |
| CI perf gates (§6), shadow verification (§7) | ❌ |

---

## PART 2 — COMPLETION PLAN (ordered, end-to-end)

### Phase 0 — Immediate hygiene (fast)
1. **Change the admin password** to a strong one (owner; the old one was weak).
2. Add missing deps to `apps/api/pyproject.toml` (email-validator, python-multipart, argon2-cffi, python-jose[cryptography], psycopg2-binary).
3. Move hardcoded pw defaults out of `settings.py` / `alembic.ini` → env only (§13).
4. Commit v2 to `feat/v2-platform` branch (reproducible deploy; `main` untouched).

### Phase 1 — Real data migration (the big one; owner runs it per §9)
5. Build the **Mongo → Postgres ETL** for the 14 entities (schema ready):
   managers, clients, trades(+dedup by fingerprint), uploads(+rejects), dividends,
   corporate_actions, watchlists(+entries), board_items, tags(+trade_tags), trade_notes,
   stock_theses, benchmarks(+values), securities, eod_prices.
6. **Owner runs** the ETL on the box; agent produces a **row-count reconciliation** (Mongo vs
   Postgres per entity) — counts only, no PII.
7. Run `portfolio-worker --recompute-all` over the real ledger → populate `portfolio.*`.
8. **Shadow-verify** (§7/R5): compare v2 metrics vs v1 for a sample of real clients before trusting.

### Phase 2 — Market data on Yahoo (no broker)
9. **Build the Yahoo provider** (the v2 `quote-poller` is currently a stub with no fetch code) —
   port v1's Yahoo path so `quote-poller` fetches prices → `redis-cache`, and the `market`
   module + `positions_latest` get live/last prices. Without this, v2 shows no live prices at all.
10. Deploy + enable the **non-broker workers**: `portfolio-worker`, `ingest-worker`,
    `eod-worker`, `scheduler` (systemd, `/etc/pi/*.env` with `pi_worker` role). Keep
    `quote-poller` on Yahoo; leave `orb-feed` **off** (no broker feed).

### Phase 3 — Feature parity gaps
11. **Manager aggregation** endpoints + UI (`manager_daily` rollups).
12. **Admin / client-manager management** (create managers/clients, assign) — API + UI.
13. **Screener** — port v1's ranked screener; decide its data source under "no broker /
    Yahoo" (v1's screener reads the ORB 1m→1d rollup — see Phase 4).
14. **Sectors / R&D** module.

### Phase 4 — ORB subsystem (largest new build)
15. Design + create the **`orb.*` schema** (candles_1m/1d, universe, signals, journal, calendar).
16. Migrate v1 ORB data (or re-derive); wire the **1m→1d rollup** that feeds the screener.
17. `orb-feed` stays off until brokers are added; ORB screener can run off migrated/rolled data.

### Phase 5 — Hardening / done
18. RS256 for JWT (ADR-0006). 19. Frontend polish (tokens, virtualization, 4-states, gen:api).
20. Perf gates (§6) measured. 21. Broker re-enable path documented (when Angel creds added:
    single identity, coordinate with v1 §10).

---

## Current live state (reference)
- `https://v2.sarey.tech` — auth-gated preview, real precompute pipeline proven on **synthetic**
  data (2 clients). API returns 401 without token.
- Workers: only `pi-api` runs. Redis + Postgres ready. Nothing broker-connected.
