# Portfolio Intelligence v2 — Low-Level Design: Backend (Python)

**Runtime:** Python 3.12 · FastAPI · uvicorn (uvloop + httptools) · asyncpg · redis-py (asyncio) · orjson · Pydantic v2 · Polars (workers only) · APScheduler
**Parent:** [HLD](HLD.md) · **DB:** [LLD-database](LLD-database.md) · **Cache:** [LLD-cache](LLD-cache.md) · **Rules:** [DOMAIN-RULES](../DOMAIN-RULES.md)

---

## 1. Repository layout

v1 (`backend/`, `frontend/`) stays **frozen** (bug fixes only) until cutover. v2 is built beside it. Top-level layout is decided in ADR-0001.

```text
apps/
  api/                          # FastAPI modular monolith  (port 8200)
    pi_api/
      main.py                   # app factory, lifespan (pools), router mounting
      settings.py
      core/                     # config, db pool, cache helper, events, auth, http, logging, telemetry
      modules/
        auth/  tenancy/  ledger/  market/  portfolio/  research/  ops/
          router.py             # thin: parse → service → respond
          service.py            # orchestration, cache-aside, authorisation
          repository.py         # SQL only (named .sql files), returns records
          schemas.py            # Pydantic request/response models  ← the OpenAPI contract
          sql/*.sql
  workers/
    pi_workers/
      quote_poller.py  portfolio_worker.py  eod_worker.py  ingest_worker.py  orb_feed.py  scheduler.py
      adapters/ (angel.py, kite.py, yahoo.py, nse.py, brokers/{zerodha.py, upstox.py})
libs/
  pi_core/                      # PURE domain library (no I/O, no clock, no globals)
    pi_core/
      engine/   fifo.py  corporate_actions.py  segments.py  matching.py
      series/   daily.py  twr.py  benchmark.py  calendar.py  downsample.py
      metrics/  returns.py  risk.py  xirr.py  capital.py  drawdown.py
      analytics/ allocation.py  concentration.py  round_trips.py  trade_stats.py
      orb/      bars.py  calendar.py  features.py  signals.py  strategy.py     # ported in Phase 5
migrations/                     # Alembic
tests/{unit,property,golden,integration,contract,load}/
infra/{systemd,nginx,postgres,redis}/
backend/  frontend/             # v1, frozen
```

## 2. Layering rules

`router → service → repository → DB`, plus `pi_core` called by **workers** (and by the API only for tiny pure calculations such as the net-return calculator).

| Layer | May | May not |
|---|---|---|
| router | validate input, call one service, shape the HTTP response | touch SQL, cache, Redis, providers |
| service | authorise, cache-aside, merge live prices, orchestrate repositories | import FastAPI types beyond `HTTPException`; call providers |
| repository | run named SQL, map rows | know about HTTP or Redis |
| `pi_core` | compute | do I/O, read the clock (`today` is a parameter), hold state |
| worker | call providers, write derived tables, publish events | serve HTTP |

Size limits (ruff `C901`/`PLR0915`): module ≤ 300 lines, function ≤ 50 lines, complexity ≤ 10. v1's `portfolio.py` is 1,419 lines and `analytics.py` 1,832; neither shape is allowed in v2.

## 3. `pi_core`: the domain library

Everything correctness-critical lives here, tested without a database.

| Module | Responsibility | Rule |
|---|---|---|
| `engine.fifo` | single-pass FIFO over a merged, ordered stream of trades and corporate-action events; emits a **daily state** stream | R7, R8 |
| `engine.matching` | classify each sell as fully / partly / un-matched; return `matched_trades` and the unmatched report | R7 |
| `engine.segments` | split delivery equity / intraday / derivatives; missing segment ⇒ equity | R9 |
| `series.daily` | expand the daily state over the trading calendar and value it with as-traded closes | R11, R17 |
| `series.twr` | time-weighted NAV with the execution-price-weighted capital base; flat-holds a day whose base < ₹1; caps a daily return ≤ −100 % as a data error | R2, R16 |
| `series.benchmark` | index-units method; `pnl = units × price − net_invested` | R10 |
| `metrics.capital` | `peak_capital`, `open_cost`, `return_on_capital` | R1 |
| `metrics.returns` | total return, CAGR (**None** under 365 days), annualisation | R3 |
| `metrics.risk` | volatility (√252 on daily obs), Sharpe from daily excess returns, drawdown, beta (date-aligned), alpha (Jensen) | R3, R11 |
| `metrics.xirr` | money-weighted return; suppressed by policy under one year | R4 |
| `analytics.*` | allocation (peak capital per closed symbol, never summed legs), concentration, round trips, win rate by *trade* not lot | R5 |

### 3.1 The single-pass engine (fixes the O(trades²) cost)

v1 re-derives positions from scratch for every trade-day. v2 walks the ledger **once**:

```text
inputs : matched trades (date, side, qty, price, charges), corporate-action events, trading calendar, price lookup
state  : per-symbol deque of open lots, cumulative realised, cumulative net cash
loop   : for each market day d in [first_trade, today]:
           apply corporate actions with ex_date == d          (before same-day trades)
           apply d's trades (buys before sells within the day)
           value open lots at close(d); record market_value, open_cost, net_invested, realised,
                                        twr_base, day_return, nav
cost   : O(T + D × S)   T = trades, D = market days, S = open symbols on the day
```

For the largest real client (4,219 trades, 1,435 days, ~16 open symbols) that is roughly 30 k valuation steps, a few milliseconds of work against v1's full recomputation per trade-day.

### 3.2 Purity contract

No `datetime.now()`, no `random`, no network, no `os.environ`, no module-level mutable state. Inputs are dataclasses or Polars frames; outputs are dataclasses. A test asserts `pi_core` imports nothing from `asyncpg`, `redis`, `httpx`, `fastapi`.

## 4. API design

### 4.1 Conventions

| Topic | Rule |
|---|---|
| Versioning | `/api/v1/...`; OpenAPI at `/api/v1/openapi.json` |
| Types | every response has a Pydantic model; the frontend types are **generated**, never hand-written |
| Units | rupees as strings-or-decimals with 2 dp; ratios as **decimals**; dates ISO `YYYY-MM-DD` |
| Series | **columnar**: `{"t":[…],"series":{"pnl":[…],"nifty_50":[…]}}`; ≤ 800 points via LTTB; full resolution only on explicit zoom |
| Lists | keyset pagination (`cursor`), never `OFFSET` |
| Freshness | every live-price response carries `as_of`, `stale`, `source` per symbol |
| Errors | `{"error":{"code","message","request_id","details"}}`; 400/401/403/404/409/422/429/503 |
| Caching | `ETag` + `Cache-Control: private, max-age=30, stale-while-revalidate=300`; live prices `max-age=5` |
| Compression | brotli/gzip at nginx; none in Python |
| Downloads | authenticated `fetch` → blob; never a bare anchor (v1's Playbook export returned 401 because of this) |

### 4.2 Consolidated reads (the fan-out fix)

v1's client dashboard fires 19 independent requests, several of which recompute the same holdings. v2 serves the first paint from **four**:

| Endpoint | Returns |
|---|---|
| `GET /clients/{id}/overview` | cards (capital deployed, current invested, realised, unrealised, return on capital), health, warnings (unmatched sells, unpriced symbols), counts |
| `GET /clients/{id}/series?from&to&points` | columnar portfolio + benchmark series |
| `GET /clients/{id}/positions` | holdings with live price, age and staleness flags |
| `GET /clients/{id}/metrics` | CAGR/total return, volatility, Sharpe, drawdown, beta, alpha, XIRR, observation count |

Everything else (allocation, trade analytics, playbook, dividends, corporate actions, calendar) loads **lazily when its tab opens**.

### 4.3 v1 → v2 route map (114 v1 routes)

| v1 router (routes) | v2 module | Notes |
|---|---|---|
| `auth` (3) | `auth` | RS256 + refresh cookie; `/me` |
| `admin` (5) | `tenancy` | managers CRUD; super-admin is a user row |
| `clients` (12) | `tenancy`, `ledger` | client CRUD; upload; **tradebook export** (new, built); uploads list |
| `portfolio` (48) | `portfolio`, `ledger` | overview/series/positions/metrics; allocation; trade analytics; playbook (+export); P&L calendar; dividends; tags/journal; manual trades; corporate actions |
| `watchlists` (19) | `research` | consolidated; same behaviour |
| `board` (4) | `research` | |
| `sectors` (4), `screener` (3) | `research` | screener reads `screener_snapshots` |
| `orb` (8) | `research` (read) + `orb-feed` (write) | live state via Redis; history from Timescale |
| `corporate_actions` (4) | `ledger` | refresh runs in `eod-worker` |
| `broker` (1), `portfolio_viewer` (2) | `ledger` / `ops` | Kite: `holdings()`, daily trade poll (v1 used `positions()` and `orders()`, both wrong for history) |
| `market` (1) | `market` | freshness + health |

## 5. Authentication and authorisation

- `POST /auth/login` → argon2id verify → `{access_token}` (RS256, 15 min, claims `sub`, `role`, `mid` or `cid`) + `Set-Cookie: rt` (httpOnly, Secure, SameSite=Strict, 7 d, rotating).
- Services verify tokens **locally** with the public key; no call per request.
- Access rules (enforced in the service layer, before any cache read):

| Role | May read | May write |
|---|---|---|
| `super_admin` | everything | managers, users, system settings |
| `manager` | own clients only | own clients' uploads, trades, notes, watchlists |
| `client` | own record only | nothing (read-only) |

- Login is rate-limited (5/min per IP and per email) and audited. There is no shared password in an env file.

## 6. Workers

All workers: structured logs, `/healthz` + `/metrics` on a local port, a row in `ops.job_runs` per run, timeouts on all I/O, jittered retries only for idempotent calls.

### 6.1 `quote-poller`

```text
every 10 s during 09:00–15:45 IST (holiday-aware via trading_calendar):
  symbols = held ∪ watchlist  (from Postgres, cached 60 s)
  for batch of ≤ 50 grouped by exchange:            # exchange-correct Angel token (R6)
      rows = angel.getMarketData("FULL", batch)      # FULL carries exchTradeTime
      for r in rows:
          if age(r.exchTradeTime) > FRESHNESS_LIMIT:  reject → dq_issue, try Yahoo, else leave to EOD close
          else HSET q:{exch}:{sym}
  update qstat
```

`FRESHNESS_LIMIT` is 7 days for the daily-close fallback and a much tighter bound in market hours. This is the systematic fix for the frozen-feed bug (VENUSREM at ₹1,797.50 for three months).

### 6.2 `eod-worker`

**Primary source: roll up the day's real 1-minute bars** from `market.candles_1m` into EOD closes, using only non-synthetic bars and skipping incomplete sessions (the behaviour of v1's `orb_daily_rollup.py`, kept idempotent). This costs **zero broker calls** and cannot disturb the live feed's Angel session. Angel/Yahoo are asked **only for gaps**: BSE-only holdings, symbols outside the feed's universe, and history from before the feed existed (a one-time backfill, converted to as-traded per R17). Benchmarks and corporate actions are fetched the same way. Then gate before loading:

| Gate | Action on failure |
|---|---|
| Close > 0, not `NaN` | drop + `dq_issue` |
| Date is an open session | drop |
| Day-over-day move > 40 % with no corporate action | hold + `WARN` for review |
| Source is split-adjusted | convert using `corporate_actions` or flag `adjusted=true` (R17) |
| Benchmark last date more than 2 sessions behind | `BLOCK` + alert (R10) |
| Symbol returns nothing for 3 consecutive sessions | mark for review |

Then `COPY → staging → MERGE`, then publish `prices.published`.

### 6.3 `portfolio-worker`

```text
on trades.changed{client}  → full recompute for that client
on prices.published{date}  → append the day's row for every client holding a changed security
on corporate action        → full recompute for affected clients

recompute(client):
   ledger  = load trades (raw), actions, cost-basis adjustments
   matched = engine.matching.matched_trades(ledger, actions)          # R7
   eq, fo  = engine.segments.split(matched)                            # R9
   states  = engine.fifo.run(eq, actions, calendar)                    # single pass
   daily   = series.daily.value(states, eod_prices)                    # R11, R17
   nav     = series.twr.build(daily)                                   # R2, R16
   bench   = {b: series.benchmark.build(matched, b_values) for b in active benchmarks}   # R10
   metrics = metrics.*(nav, bench)                                     # R3, R4
   write portfolio.* in ONE transaction; then refresh manager rollup; then INCR ver:client:{id}
```

Idempotent: it derives everything from the ledger, so replaying an event yields the same rows.

### 6.4 `ingest-worker`

`Fetch raw → store unchanged → detect broker format → adapter.parse → validate → keep every column → load → publish`.

- Broker adapters (`zerodha`, `upstox`) implement one `BrokerAdapter` protocol; unknown headers are kept in `trades.extra`, not dropped.
- Rejected rows go to `ledger.upload_rejects` with the reason. The upload summary reports imported, duplicate and rejected counts that add up to `rows_total`.
- `Auction`, `charges` and price-0 rules are explicit (charges `NULL` = unknown; price 0 only from manual entry).
- Kite sync: `holdings()` for reconciliation (R18), a daily trades poll for new fills. It cannot backfill history, and the docs say so.

### 6.5 `orb-feed`

The ORB engine (`services/orb/*`, ~2,700 lines with its own tests) is ported **unchanged in behaviour** in Phase 5 and runs as its own process. It writes bars to `market.candles_1m` and publishes signals; the API only reads. It is the one process with a calendar restart rule.

### 6.6 `scheduler`

APScheduler with the `lock:scheduler` leader lock. IST schedule: `jobs.eod` 15:45 (retry hourly until complete), NAV-style retries 07:00, corporate actions 18:00, weekly full recompute Sunday 02:00, candle compression is a Timescale policy.

## 7. Provider adapters

```python
class MarketDataProvider(Protocol):
    name: str
    async def quotes(self, keys: list[SecurityKey]) -> dict[SecurityKey, Quote]: ...
    async def daily_bars(self, key: SecurityKey, start: date, end: date) -> list[Bar]: ...
```

One circuit breaker (opens after 5 consecutive failures) per provider. **Only workers construct providers.** A lint rule forbids importing an adapter from `modules/`.

**Angel session ownership (open spike S-1).** Angel's login is a scarce, shared resource. v1 keeps one session in one process; v2 has several processes that need Angel. Design under test:

```text
AngelSessionManager
  owner   = the process holding lock:angel-session (leader-elected; normally orb-feed)
  login   = once per day + on auth error; writes {jwt, refresh, feed_token, issued_at} to redis-streams (noeviction)
  others  = read the tokens from Redis, build a SmartConnect with them, and NEVER call generateSession themselves;
            on an auth error they set angel:relogin-requested and wait for the owner
  limiter = a Redis token bucket per Angel endpoint, shared by every process (a per-process limiter would multiply the rate)
```

If Spike S-1 shows Angel allows concurrent sessions, this simplifies to per-process sessions with the shared limiter. Either way there is **one production Angel identity in one place**; staging/local never use it.

## 8. Testing

| Level | Tooling | Scope | Gate |
|---|---|---|---|
| Unit | pytest | `pi_core` | ≥ 90 % coverage on `pi_core` |
| **Property** | hypothesis | (a) deposits/withdrawals never change NAV; (b) staged vs lump-sum deployment on the same price path give the same NAV; (c) `client pnl = market_value − net_invested` (R10 identity); (d) NAV > 0 always; (e) manager total = Σ clients | required |
| **Golden** | pytest + fixtures | real, anonymised books (including the 4,219-trade client and the near-empty-portfolio re-entry that broke the first TWR draft) | exact to ₹0.01 |
| Integration | pytest + ephemeral Postgres database (a template DB, no Docker needed) | repositories, `MERGE`, migrations, `EXPLAIN` Q1–Q8 | required |
| Contract | schemathesis + OpenAPI snapshot | every route | required |
| Load | k6 against staging with the migrated real dataset | N1–N4 | before cutover |
| Static | ruff, mypy `--strict` on `pi_core` and `core` | all | required |

The v1 suites (`test_engine.py` and friends, plus the new TWR / peak-capital / pricing / export tests) are **ported as the first golden set**.

## 9. Performance checklist

- [ ] uvicorn with `--loop uvloop --http httptools`, N workers
- [ ] `default_response_class=ORJSONResponse`; hot paths return pre-serialised `bytes`
- [ ] no `SELECT *`; named SQL in `.sql` files; `statement_timeout` 2 s on the API role
- [ ] Redis socket timeout 50 ms; cache failures fall through
- [ ] no provider call and no `pi_core` computation on a request path (except the calculator)
- [ ] `EXPLAIN` gate for Q1–Q8; k6 gate for N1–N4
- [ ] `py-spy` profile attached to any PR touching a hot path
