# Portfolio Intelligence v2 — Low-Level Design: Cache and Events (Redis)

**Engine:** Redis 7, **two instances** (ports 6390 / 6391; quest-mf owns 6379) · **Parent:** [HLD](HLD.md) · **Storage:** [LLD-database](LLD-database.md)
**Replaces:** the eleven per-process dict caches listed in the [audit §4](../00-CURRENT-STATE-AUDIT.md).

---

## 1. Principles

1. **Cache is an accelerator, never a dependency.** Postgres serves the precomputed row in single-digit milliseconds, so a cold or empty cache must still meet the latency targets (HLD N1–N4). If Redis is down, requests fall through to Postgres and succeed.
2. **Versioned keys, never deletion.** A recompute bumps a version counter; old keys simply stop being read and expire. No `KEYS`, no `SCAN`-and-`DEL`, no stampede on invalidation.
3. **Authorise before you read the cache.** Access checks (`user → client`) run first. The cache key does not contain the user, so a cache hit can never bypass authorisation.
4. **Live data is not versioned data.** Prices change every few seconds. They live in their own keys and are merged at response time, so they never invalidate (or get baked into) a cached payload.
5. **One mechanism.** Every cached read goes through `core.cache.cached_bytes`. A second ad-hoc cache is a review failure.

## 2. Two instances (why)

| Instance | Port | Policy | Holds | Why separate |
|---|---:|---|---|---|
| `redis-cache` | 6390 | `maxmemory 256mb`, `allkeys-lru` | cached payloads, live quotes, rate limits, locks | eviction is *desired* here |
| `redis-streams` | 6391 | `noeviction`, AOF `everysec` | job/event streams, dead letters, **version counters (`ver:*`)**, Angel session tokens | an evicted event is a lost job; an evicted version counter resets to 0 and can resurrect a stale payload |

One instance cannot be both: `allkeys-lru` would evict events, `noeviction` would make the cache fill and then fail writes. Two cheap processes remove the conflict.

## 3. Cache layers (outermost first)

| Layer | What | TTL | Invalidated by |
|---|---|---|---|
| **L0 browser** (TanStack Query + HTTP `ETag`) | JSON responses | per data class, §7 | new `as_of` in the key; `ETag` → `304` |
| **L1 nginx** | static assets only (hashed, `immutable`). **No API microcache**: responses are per-user, so it would add risk for little gain. | 1 year | new build hash |
| **L2 Redis** | pre-serialised response bytes | 24 h (safety net) | version bump |
| **L3 Postgres** | the precomputed `portfolio.*` rows | permanent | worker recompute |
| **L4 raw** | provider payloads, tradebooks, Parquet | permanent | — |

## 4. Key registry (single source of truth)

### 4.1 Versions (stored in `redis-streams`, never in the evicting cache)

A version counter must **not** be evictable: if `ver:client:X` were evicted from an LRU instance it would read as 0 and a payload still cached under version 0 (TTL 24 h) would be served as current. Counters therefore live in the `noeviction` instance; only the payloads they name live in `redis-cache`.

| Key | Type | Bumped by | Meaning |
|---|---|---|---|
| `ver:client:{client_id}` | int | `portfolio-worker`, after it publishes that client | every client-scoped payload |
| `ver:manager:{manager_id}` | int | `portfolio-worker`, after rollups refresh | every manager-scoped payload |
| `ver:prices` | int | `eod-worker` on `prices.published` | price-derived shared data |
| `ver:research` | int | screener / research publishers | screener, sector research |

### 4.2 Cached payloads (`redis-cache`, bytes, TTL 24 h)

| Key pattern | Content | Built from |
|---|---|---|
| `ov:{ver}:{client_id}` | client overview (static part) | Q1 |
| `ser:{ver}:{client_id}:{from}:{to}:{pts}` | performance series, **columnar**, ≤ 800 pts | Q2 + LTTB |
| `met:{ver}:{client_id}` | metrics (CAGR/total return, vol, Sharpe, drawdown, beta, alpha, XIRR) | `client_metrics` |
| `pos:{ver}:{client_id}` | positions (static: qty, cost, entry) | Q4 |
| `ta:{ver}:{client_id}` | trade analytics | `trade_analytics` |
| `mov:{ver}:{manager_id}` | manager overview | manager rollup |
| `mser:{ver}:{manager_id}:{from}:{to}:{pts}` | book series + per-client return series | Q3 |
| `sec:{prefix}` | symbol search typeahead (TTL 1 h) | Q8 |
| `scr:{ver}:{model}:{hash}` | screener page | `screener_snapshots` |

`{ver}` is the integer read from the matching `ver:*` key at request time. `{hash}` is `sha1` of the canonicalised query.

### 4.3 Live market data (`redis-cache`)

| Key | Type | TTL | Fields |
|---|---|---:|---|
| `q:{exch}:{symbol}` | hash | **300 s** | `ltp`, `close`, `prev_close`, `ts` (exchange trade time), `src`, `age_s` |
| `qsym:held` | set | 120 s | symbols to poll, published by the poller from Postgres |
| `qstat` | hash | none | `last_ok_ts`, `last_error`, `symbols_ok`, `symbols_rejected` |

The 300 s TTL is deliberate: if the poller dies, quotes **expire** and responses flip to `stale=true` with the last EOD close, instead of silently serving hours-old prices. Keys are `{exch}:{symbol}`, never `{symbol}` alone (DOMAIN-RULES R6).

### 4.4 Coordination and limits

| Key | Type | TTL | Purpose |
|---|---|---:|---|
| `lock:scheduler` | string | 30 s, renewed | leader election |
| `lock:job:{name}:{date}` | string | job max | one run per job per day |
| `evt:{event_id}` | string `NX` | 24 h | consumer de-duplication |
| `rl:{route}:{subject}` | counter | 60 s | application rate limit (backup to nginx) |
| `rt:revoked:{jti}` | string | token lifetime | refresh-token revocation |

### 4.5 Streams (`redis-streams`, `MAXLEN ~ 100000`)

| Stream | Producer | Consumers | Payload |
|---|---|---|---|
| `jobs.ingest` | api (upload), scheduler | ingest-worker | `{upload_id \| source, business_date}` |
| `trades.changed` | ingest-worker, api (manual trade) | portfolio-worker | `{client_id}` |
| `jobs.eod` | scheduler | eod-worker | `{business_date}` |
| `prices.published` | eod-worker | portfolio-worker | `{business_date, security_ids?}` |
| `portfolio.published` | portfolio-worker | api (metrics only) | `{client_id, as_of}` |
| `*.dlq` | any consumer after 5 failed deliveries | ops | original event + error |

Every event is `{event_id, type, occurred_at, producer, schema_version, payload}`. Handlers are **idempotent** and de-duplicate on `event_id`.

## 5. The one caching helper

```python
async def cached_bytes(ns: str, ver_key: str, key_parts: tuple, ttl: int,
                       loader: Callable[[], Awaitable[bytes]]) -> tuple[bytes, str]:
    """Return (payload, etag). Falls through to `loader` on any Redis problem."""
    try:
        ver = await redis_ver.get(ver_key) or b"0"             # redis_ver = the noeviction instance
        key = f"{ns}:{ver.decode()}:{sha1(canon(key_parts)).hexdigest()}"
        if (hit := await redis.get(key)) is not None:
            return hit, etag_of(key)
        async with redis.lock(f"lk:{key}", timeout=5, blocking_timeout=2):   # stampede guard
            if (hit := await redis.get(key)) is not None:
                return hit, etag_of(key)
            data = await loader()                                          # Postgres SELECT + orjson
            await redis.set(key, data, ex=ttl)
            return data, etag_of(key)
    except RedisError:
        metrics.cache_errors_total.inc()
        return await loader(), ""                                          # degrade, never fail
```

Redis socket timeout 50 ms. Responses are returned as pre-serialised `bytes` (no re-encode on a hit).

## 6. Invalidation matrix

| Event | Bumps | Recompute scope |
|---|---|---|
| Tradebook imported / manual trade / delete | `ver:client:{id}`, `ver:manager:{m}` | that client only |
| `prices.published` (EOD) | `ver:prices`, then `ver:client:*` for clients that hold a changed security, `ver:manager:*` | one appended row per client |
| Corporate action ingested | `ver:client:{id}` for clients holding the ISIN | full re-run for those clients (quantities change) |
| Cost-basis adjustment added | `ver:client:{id}` | that client |
| Benchmark values published | `ver:prices` | benchmark rows only |
| Screener published | `ver:research` | — |

The intraday quote poller never bumps anything: quotes are read live, outside versioned payloads.

## 7. Client-side (TanStack Query) freshness by data class

| Class | `staleTime` | Refresh |
|---|---:|---|
| Series, metrics, trade analytics (change once a day or on upload) | 5 min | key includes `as_of`, so a new publish is a new cache entry |
| Overview, positions | 30 s | refetch on window focus |
| Live quotes | 10 s | poll **only** while the tab is visible and the market is open; stop otherwise |
| Reference (categories, symbols) | 1 h | — |

## 8. Failure modes

| Failure | Behaviour |
|---|---|
| `redis-cache` down | `cached_bytes` falls through to Postgres; latency rises to the miss path (still inside targets); live prices switch to last EOD close, flagged `stale` |
| `redis-streams` down | uploads return `503` for the async step; nothing is lost silently; workers resume from the consumer-group offset |
| Poller dead | `q:*` keys expire in ≤ 5 min → `stale=true` |
| Provider returns a frozen/old quote | rejected by the poller's freshness gate; symbol falls back Yahoo → last EOD close, flagged |
| Worker crash mid-event | event stays pending → re-delivered → idempotent handler; after 5 tries → `.dlq` + `ops.dq_issues` |
| Event storm (bulk import) | events are per client and coalesced; the worker recomputes each client once per burst |

## 9. Sizing and monitoring

Working set is tiny: ~6 payloads per client × ≤ 100 KB (compressed columnar) ≈ 0.6 MB per client. **100 clients ≈ 60 MB.** `maxmemory 256mb` has 4× headroom.

| Metric | Alert |
|---|---|
| Cache hit ratio (`hits/(hits+misses)`) | < 80 % for 15 min (warns; not an outage) |
| `cache_errors_total` rate | > 0 sustained |
| Stream lag (`XPENDING`) | > 100 messages or > 60 s old |
| `.dlq` length | > 0 |
| Quote age p95 (market hours) | > 30 s |
| `qstat.last_ok_ts` | older than 60 s in market hours |

## 10. Anti-patterns (rejected in review)

- A module-level `dict` or `lru_cache` holding request-derived data.
- Cache keys without a version.
- `redis.keys()`, `scan`-then-`delete`.
- Putting a user id into a shared cache key (authorise first instead).
- Baking live prices into a versioned payload.
- Any provider call (Angel, Yahoo, NSE) from an API request.
- Treating a cache miss as an error.
