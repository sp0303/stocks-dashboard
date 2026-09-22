# 0003. Precompute Derived Data, Own the Price Store, Poll Quotes Out of Band

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` HLD D1 and AGENTS §3.1; `docs/v2/00-CURRENT-STATE-AUDIT.md` §2, §3

---

## 1. Context and Problem Statement

Measured on the real dataset, cold requests take 0.9–7 s and warm ones 1–70 ms. The cold path (a) recomputes the FIFO engine once per trade-day and (b) calls Angel One then Yahoo for quotes and history inside the request. Yahoo returned HTTP 429 during testing. A frozen Angel record (VENUSREM) was served as live for three months, overstating a book by ₹48,658.

## 2. Decision Drivers

- Cold = warm: targets are met with **no cache**.
- A provider outage or a rate limit must never break a page.
- Bad or stale prices must be caught **at ingest**, once, not on every read.

## 3. Decision

1. **Precompute.** `portfolio-worker` writes per-client daily series, positions, metrics and manager rollups (`portfolio.*`). The API reads them with primary-key lookups.
2. **Own the price data.** `market.eod_prices` and `market.candles_1m` are our tables. **Daily closes are rolled up from the live ORB 1-minute feed** (the project owner's standing preference; v1 already does this nightly), with Angel/Yahoo used only for gaps (BSE-only symbols, pre-feed history). Providers are called **only by workers**; a lint rule forbids importing a provider from an API module.
3. **Quote poller.** One worker batch-polls the union of held and watched symbols during market hours and writes `q:{exchange}:{symbol}` with the exchange trade time to Redis (TTL 300 s). Requests merge live prices from Redis and, if a quote is missing or expired, fall back to the last EOD close with `stale=true`.
4. **Ingest gates.** Freshness, sanity (non-positive, non-session, > 40 % move without a corporate action), as-traded vs adjusted (R17), and benchmark staleness (R10) are enforced when data enters, and failures become `ops.dq_issues`.
5. **Single-pass engine** in `pi_core`: cost O(T + D·S) instead of per-day recomputation.

## 4. Consequences

**Positive:** predictable latency independent of cache state; provider failure degrades to "stale, flagged" instead of an error; the frozen-feed class of bug is eliminated in one place; the poller makes one call per 50 symbols per 10 s regardless of how many users are online.
**Negative / cost:** a backfill of as-traded closes for every held symbol; a small amount of read-time merging (live price × quantity) in the API; workers must be monitored.
**Rejected:** caching the compute (still slow on every miss and every restart); per-request provider calls with a longer TTL (the v1 approach; shifts the problem, does not remove it).
