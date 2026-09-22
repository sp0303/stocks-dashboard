# 0004. Redis: Two Instances, Versioned Cache Keys, Streams for Events

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` HLD D3/D9, LLD-database §7, AGENTS §3 rules 5, 6, 9

---

## 1. Context and Problem Statement

v1 has no Redis and **eleven** independent in-process caches with different TTLs (10 min, 15 min, 30 min, 6 h). They are lost on restart, not shared across workers, and invalidated only by time. The quote cache was keyed by symbol alone, so it could serve one exchange's price for another's.

## 2. Decision

1. **Two Redis 7 instances:** `redis-cache` (6390, `allkeys-lru`, `maxmemory 256mb`) and `redis-streams` (6391, `noeviction`, AOF `everysec`). One instance cannot serve both needs (eviction is desired for a cache and fatal for events). Ports avoid quest-mf's 6379.
2. **Versioned keys, never deletion.** Payloads live at `{ns}:{ver}:{hash}`; a recompute bumps `ver:client:{id}` / `ver:manager:{id}` / `ver:prices`. **The counters live in the `noeviction` instance** (an evicted counter would reset to 0 and resurrect a stale payload); only the payloads live in the LRU cache. No `KEYS`, no `SCAN`-and-delete.
3. **One helper** (`core.cache.cached_bytes`) for every cached read; stampede lock; falls through to Postgres on any Redis error.
4. **Authorise before reading the cache**; keys never contain a user id.
5. **Live quotes are not versioned data**: `q:{exch}:{sym}` hashes with a 300 s TTL so a dead poller makes quotes expire visibly.
6. **Streams** carry events (`trades.changed`, `prices.published`, `jobs.*`) with consumer groups, idempotent handlers deduplicating on `event_id`, and dead-letter streams after 5 failed deliveries.
7. **No microcache in nginx for the API** (responses are per-user).

## 3. Consequences

**Positive:** one caching mechanism, invalidated precisely by events; restart-proof; observable (hit ratio, stream lag); a Redis outage costs latency, not correctness (the miss path still meets targets because Postgres serves precomputed rows).
**Negative / cost:** two more processes to run and monitor; the working set is small (~0.6 MB per client) so memory is not a concern.
**Rejected:** a single Redis (policy conflict); Kafka/OCI Streaming (far heavier than the event volume needs); keeping per-process caches (the current problem).
