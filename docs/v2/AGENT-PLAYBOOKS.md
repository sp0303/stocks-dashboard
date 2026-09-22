# v2 — Agent Playbooks

Recipes for the common tasks, so an agent (or a human) does them the same way every time. They implement [AGENTS.md](../../AGENTS.md); if they disagree, **AGENTS.md wins**.

**Every task starts the same way:** read the relevant HLD/LLD section, read the DOMAIN-RULES that apply, state the plan in two or three lines, and identify which rule (R1–R18) or gate (N1–N14) the change touches.
**Every task ends the same way:** run the checks, **show the output**, and report anything skipped or failing. Never say "tested" without having run it.

---

## P1. Add or change a metric

1. Write or find the rule in `DOMAIN-RULES.md`; if it is new, add it (and an ADR if it changes a decision) **before** code.
2. `pi_core/metrics/…`: write the failing test first: a **golden** case from a real book and a **property** (e.g. flows never change NAV).
3. Implement as a pure function. No I/O, no clock, one place.
4. Wire it into `portfolio-worker`; write the result to the right `portfolio.*` table (add an expand-only migration if needed: P3).
5. Expose it through the existing `overview`/`metrics` response (Pydantic model → OpenAPI). Ratios stay **decimals** (R12).
6. `npm run gen:api`; render it with the shared formatter (`Percent`, `Money`). Never multiply by 100 inline.
7. Check R5: is the same figure computed anywhere else? If so, delete the copy and read the one source.
8. Verify on the golden books **and** on a production-shaped restored dataset; look at the rendered page in the browser.

## P2. Add an API endpoint

1. Name it under `/api/v1/<module>/…`; decide the module from HLD §5.
2. `schemas.py` first (request and response models). Units per LLD-backend §4.1.
3. `repository.py` + a named `.sql` file: explicit columns, a time predicate for time series, keyset pagination. Add the query to the `EXPLAIN` gate if it is canonical.
4. `service.py`: **authorise first**, then `cached_bytes` (P4), then the repository.
5. `router.py`: parse → service → respond. No SQL, no cache, no provider call.
6. Contract test (schemathesis + snapshot) and an integration test against a real Postgres database.
7. Regenerate frontend types; add an MSW handler; add the four-state component test.

## P3. Add a database migration (expand → migrate → contract)

1. `alembic revision -m "<msg>"`, written by hand; review any autogenerate output.
2. **Expand only** in the first release: add nullable columns/tables/indexes; never drop or rename in the same release that stops using them.
3. Backfill in batches (no long locks); use `CREATE INDEX CONCURRENTLY`.
4. Migrations run **before** the new code starts and must be safe with the **previous** release running.
5. Contract (drop the old column) ships in a later release, after the old code is gone.
6. Test on a restored copy; report the timing. If it is not backward-compatible: **stop and ask**.

## P4. Add a cache key

1. Add it to the registry table in `LLD-cache.md` (pattern, content, TTL, source, version key).
2. Use `cached_bytes` with the right `ver:*`. Never write your own get/set.
3. Add the event that bumps its version to the invalidation matrix.
4. Confirm authorisation runs **before** the lookup and no user id is in the key.
5. Test the miss path meets the latency target with an empty cache (cold = warm).

## P5. Add a worker or job

1. Define the event (stream, payload, `schema_version`) in the registry; handlers are **idempotent** and dedupe on `event_id`.
2. Timeouts on all I/O; jittered retry only for idempotent calls; dead-letter after 5 tries.
3. Write a row to `ops.job_runs`; expose `/healthz` and `/metrics`.
4. State its **restart rule** in DEPLOYMENT §6. Anything touching the ORB feed's process is calendar-restricted.
5. Prove idempotency: run the handler twice and show identical rows.

## P6. Add a data source or broker adapter

1. Implement the `MarketDataProvider` or `BrokerAdapter` protocol; it lives under `workers/adapters/` and is **never imported from `modules/`**.
2. Rate-limit through the shared Redis token bucket; add a circuit breaker; store the raw payload unchanged before parsing.
3. **Every column is kept** (typed or in `extra`); rejected rows keep their reason (R13).
4. Add the freshness, sanity and as-traded checks (R6, R17) at ingest and a `dq_issue` for each failure.
5. Never log secrets; never call it from a request path.

## P7. Add a frontend feature or chart

1. New folder `features/<area>/`; expose only `index.ts`.
2. One component per file (≤ 150 lines, ≤ 40 JSX lines); pages stay composition-only.
3. Server data through TanStack Query with a key including the resource id and range; filters and tab in the URL.
4. Chart = a pure option builder in `components/charts/options/` + the `EChart` wrapper; columnar data; a "view data" table fallback.
5. All four states (loading, empty, error, data); tokens only (no hex); light and dark.
6. `npm run lint && npm run typecheck && npm test && npm run size`; attach screenshots of both themes.

## P8. "A number looks wrong": investigation order

1. Reproduce on the same data. Note client, date, expected vs shown.
2. **Is it a unit?** ×100 or a truthiness check (R12).
3. **Is it a price?** Exchange (R6), as_of, source, stale, split-adjusted (R17). Compare with the last close.
4. **Is it the ledger?** Unmatched sells (R7), segments (R9), missing charges (R15), duplicates.
5. **Is it a definition?** Which rule owns this figure? Is a second copy computing it (R5)?
6. **Is it a series?** Calendar coverage (R11), NAV sanity (R16), benchmark health (R10).
7. Reduce to a minimal case, add it as a golden fixture, then fix. Never patch a stored value by hand.

## P9. "It is slow": investigation order

1. Measure cold and warm from the browser; record the numbers.
2. Is any provider called on the request path? (must be none)
3. Is anything computed on the request path that a worker should have precomputed?
4. `EXPLAIN (ANALYZE, BUFFERS)` the canonical query; any `Seq Scan` on a large table is a bug.
5. Payload size (compressed), number of requests on first paint, cache hit ratio.
6. Attach before/after numbers to the change.

## P10. Get a production-shaped dataset (never done by an agent)

1. **The user** runs the dump on the box and copies it down. Agents do not read production or copy client data (AGENTS §9).
2. Restore into a throwaway local database; never point a dev server at production.
3. Anonymise names, client codes and emails before it is used for development or committed as a fixture.
4. Delete the dump and the restored copy when finished.

## P11. Ship a fix to v1 during the freeze

1. Only bug and security fixes; anything else goes to the v2 backlog.
2. Branch from `main`, tests first, verify on real data and in the browser.
3. **Deploy only after 15:30 IST** on a trading day, and only when the user asks. Sequence: `git pull --ff-only`, build, then restart. Never restart between 08:45 and 15:30 IST (it breaks the day's ORB feed).
4. Production is the **new OCI box only**; the old box must stay stopped and its other projects untouched.

## P12. Reporting format (every task)

```text
What changed        : files and behaviour, in plain words
Rules touched       : R-numbers / gates
Verified how        : commands run and their output; real-data check; rendered-page check
Not verified        : anything skipped, and why
Numbers             : before/after for anything on a hot path
Follow-ups          : what remains, what needs a decision
```

## PR checklist

- [ ] Layering respected; no provider call, no SQL in a router, no computation on a request path
- [ ] DOMAIN-RULES honoured (list them); new rule → docs + tests
- [ ] Tests: unit + golden/property for money logic; integration for SQL; four states for UI
- [ ] Lint, types, tests shown with output; `EXPLAIN`/size/latency gates if a hot path
- [ ] OpenAPI types regenerated; docs and (if a decision changed) an ADR updated
- [ ] Migration expand-only and backward-compatible
- [ ] No secrets, dumps, `.venv`, `node_modules`, build output committed
- [ ] Verified on production-shaped data and rendered in a browser
