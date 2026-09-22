# 0001. Target Architecture (Modular Monolith + Workers) and Repository Layout

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` HLD D4/D5/D6 and its 2026-09-17 architecture amendment; `docs/v2/00-CURRENT-STATE-AUDIT.md` §3, §6, §8

---

## 1. Context and Problem Statement

v1 is one FastAPI process that serves HTTP **and** hosts the ORB feed, the alert loop and cache warmers. Consequences measured in the audit: an API deploy can break the ORB feed (so deploys are calendar-bound, 08:45–15:30 IST is forbidden), caches are per-process, and `routers/portfolio.py` (1,419 lines) mixes routing, compute, caching and I/O.

quest-mf's HLD prescribes six microservices on six ports, but its own AGENTS.md (approved 2026-09-17) amended that to **a single modular monolith**. Its docs contradict each other; we must not copy the contradiction.

## 2. Decision Drivers

- One developer plus AI agents: operational surface must stay small.
- The API must be deployable at any time.
- Correctness-critical math must be testable without a database.
- Reuse quest-mf's conventions so the two products feel and operate alike.

## 3. Decision

1. **One deployable API** (`apps/api`, FastAPI, modular monolith) with bounded-context modules: `auth`, `tenancy`, `ledger`, `market`, `portfolio`, `research`, `ops`.
2. **Separate worker processes** sharing the same code: `quote-poller`, `portfolio-worker`, `eod-worker`, `ingest-worker`, `orb-feed`, `scheduler`. **No microservices, no inter-service HTTP.**
3. **`libs/pi_core`**: a pure domain library (no I/O, no clock, no globals) holding the engine, series, metrics and ORB logic.
4. **`orb-feed` is its own process**, so API deploys never touch it.
5. **Layout** (new top-level folders, hence this ADR): `apps/{api,workers,web}`, `libs/pi_core`, `migrations/`, `infra/`. v1 `backend/` and `frontend/` stay **frozen** (bug fixes only) until cutover, then are deleted.
6. Layering `router → service → repository`; module ≤ 300 lines, function ≤ 50, complexity ≤ 10.

## 4. Consequences

**Positive:** API restarts are safe at any time; `pi_core` is unit- and property-testable; the process model is understandable by one person; consistent with quest-mf's approved direction.
**Neutral / trade-offs:** several processes to supervise (systemd units, one table row per job in `ops.job_runs`); a shared codebase means a bad import can affect workers and API together (mitigated by CI).
**Rejected:** microservices per bounded context (operational cost with no team to justify it); keeping the feed inside the API (v1's restart hazard).
