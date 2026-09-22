# 0002. PostgreSQL + TimescaleDB Replaces MongoDB

* **Status**: Proposed (awaiting approval)
* **Date**: 2026-09-21
* **Deciders**: Project Owner
* **Consulted**: `quest-mf` HLD D2; `docs/v2/00-CURRENT-STATE-AUDIT.md` §5

---

## 1. Context and Problem Statement

v1 stores everything in MongoDB behind a 206-method `store.py` with a second, file-backed implementation for tests. There is no schema, no migrations, money is stored as floats, and there are 11 indexes in total.

The audit shows the data is **small where it matters** (8,925 trades = 4 MB; the whole derived layer will be a few MB) and **large in one place** (`orb_candles_1m`: 39 M bars, 2.2 GB, on a disk that was 75 % full).

## 2. Decision Drivers

- Correctness: `NUMERIC` money, constraints, point-in-time joins, foreign keys, migrations.
- Candle storage needs real compression and time-based retention.
- One stack across quest-mf and this product.
- **Honesty about latency:** the slowness is caused by compute and provider calls on the request path (R1, R2), not by Mongo. A database swap alone would not fix it.

## 3. Decision

Adopt **PostgreSQL 16 + TimescaleDB** as the system of record. Only `candles_1m`, `eod_prices` and `benchmark_values` are hypertables; everything else is ordinary Postgres. Schema is owned by Alembic. The `JsonStore` fallback and the `BaseStore` interface are **retired**; repositories replace them and tests run against an ephemeral Postgres database.

Sequencing matters: latency wins come from ADR-0003 and ADR-0004. The database move is scheduled **after** the golden tests exist and is verified by the ETL report (LLD-database §7). It is not on the critical path for the first speed-up.

## 4. Consequences

**Positive:** integrity by construction (a `CHECK (quantity > 0)` cannot be forgotten in application code); exact money; SQL for rollups (`manager_daily` is a `SUM`); candle storage shrinks (vendor-reported ~90 %; to be measured); one operational skill set across both products.
**Negative / cost:** a full data migration and rewrite of the persistence layer; the shared Postgres cluster needs capacity checks (Open Decision O-1, O-2); Timescale must be installed (managed OCI Postgres may not offer it, so self-hosted is assumed).
**Rejected:** staying on Mongo (workable for the small data, wrong for candles and relational rules); Postgres without Timescale (would leave the 39 M-bar table uncompressed); ClickHouse (revisit only if candles exceed ~1 B rows).
