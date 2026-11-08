"""v1 (Mongo) -> v2 (Postgres) ledger resync: managers, clients, uploads, trades, corporate
actions, dividends, theses, watchlists and MyBoard items. Incremental and idempotent.

    reader (Mongo, read-only) -> V1Data
    PgLedgerRepo.snapshot()   -> V2Snapshot           (inside the write transaction)
    plan_sync()               -> Plan                 (pure; v1_sync_ledger_plan)
    PgLedgerRepo.apply(plan)  -> COPY -> staging -> MERGE, rejects -> ops.dq_issues

``dry_run`` reads in a READ ONLY transaction and never calls ``apply``: Postgres itself
refuses any write. Orphans (v2 rows whose v1 source is gone) are reported; with
``flag_orphans`` they are soft-flagged (trade tombstone / client INACTIVE / manager
inactive), never deleted. Trade notes/tags are reconciled by
``scripts/reconcile_trade_notes_tags.py`` (called by the CLI after this runs).
Logs and reports carry counts and v2 ids only (AGENTS §9).
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from pi_workers.v1_sync_ledger_map import IST, jsonable
from pi_workers.v1_sync_ledger_plan import Plan, V1Data, V2Snapshot, plan_sync
from pi_workers.v1_sync_ledger_sql import (
    ADVISORY_LOCK,
    APPLY_ORDER,
    ORPHAN_CLIENTS_FLAG,
    ORPHAN_MANAGERS_FLAG,
    ORPHAN_TRADES_DDL,
    ORPHAN_TRADES_FLAG,
    REJECT_CHECK,
    REJECTS_DDL,
    REJECTS_INSERT,
    SNAPSHOT_SQL,
    SPECS,
    merge_sql,
    staging_ddl,
)

logger = logging.getLogger("pi_workers.v1_sync_ledger")

# The one-time migration ran on 2026-10-04; v2 trades created before this are v1-origin.
DEFAULT_CUTOVER = datetime(2026, 10, 5, tzinfo=IST)
# --flag-orphans refuses to tombstone more than this share of v1-origin trades (a wrong
# MONGODB_DB or an empty collection must not wipe a book).
MAX_ORPHAN_FRACTION = 0.05
V1_COLLECTIONS = {
    "managers": "managers", "clients": "clients", "trades": "trades", "uploads": "uploads",
    "corporate_actions": "corporate_actions", "dividends": "dividends", "theses": "thesis",
    "watchlists": "watchlists", "boards": "boards",
}


class SyncAborted(RuntimeError):
    pass


@dataclass
class SyncResult:
    dry_run: bool
    plan: Plan
    applied: Counter = field(default_factory=Counter)
    skipped_locked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"dry_run": self.dry_run, "skipped_locked": self.skipped_locked,
                "plan": self.plan.counts(), "applied": dict(self.applied),
                "changed_clients": len(self.plan.changed_clients),
                "recompute_all": self.plan.recompute_all}


def read_v1(mdb: Any) -> V1Data:
    """Every v1 collection the ledger needs, full documents (raw kept for R13)."""
    data = V1Data()
    for attr, coll in V1_COLLECTIONS.items():
        setattr(data, attr, list(mdb[coll].find({})))
    return data


def _parse_thesis(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


class PgLedgerRepo:
    """All Postgres I/O of the sync. ``conn`` is an asyncpg connection."""

    def __init__(self, conn: Any) -> None:
        self.conn = conn

    async def snapshot(self, cutover: datetime) -> V2Snapshot:
        c, q = self.conn, SNAPSHOT_SQL
        snap = V2Snapshot(
            managers=[dict(r) for r in await c.fetch(q["managers"])],
            clients=[dict(r) for r in await c.fetch(q["clients"])],
            trades=[dict(r) for r in await c.fetch(q["trades"], cutover)],
            uploads=[dict(r) for r in await c.fetch(q["uploads"])],
            corporate_actions=[dict(r) for r in await c.fetch(q["corporate_actions"])],
            dividends=[dict(r) for r in await c.fetch(q["dividends"])],
            theses=[{**dict(r), "thesis": _parse_thesis(r["thesis"])} for r in await c.fetch(q["theses"])],
            watchlists=[dict(r) for r in await c.fetch(q["watchlists"])],
            watchlist_entries=[dict(r) for r in await c.fetch(q["watchlist_entries"])],
            board_items=[dict(r) for r in await c.fetch(q["board_items"])],
        )
        snap.reject_keys = {r["entity_key"] for r in await c.fetch(q["reject_keys"], REJECT_CHECK)}
        return snap

    async def _merge(self, entity: str, rows: list[dict]) -> int:
        spec = SPECS[entity]
        await self.conn.execute(staging_ddl(spec))
        await self.conn.execute(f"TRUNCATE {spec.staging}")
        records = [tuple(_cell(r.get(c)) for c in spec.names) for r in rows]
        await self.conn.copy_records_to_table(spec.staging, records=records, columns=spec.names)
        status = await self.conn.execute(merge_sql(spec))
        return _rowcount(status)

    async def apply(self, plan: Plan, flag_orphans: bool) -> Counter:
        out: Counter = Counter()
        for entity in APPLY_ORDER:
            p = plan[entity]
            rows = p.inserts + p.updates
            if rows:
                out[f"{entity}_merged"] = await self._merge(entity, rows)
        if plan.new_rejects:
            await self.conn.execute(REJECTS_DDL)
            recs = [(r.key, json.dumps({"reason": r.reason, "raw": jsonable(r.raw)}, sort_keys=True))
                    for r in plan.new_rejects]
            await self.conn.copy_records_to_table("stg_v1_rejects", records=recs,
                                                  columns=["entity_key", "details"])
            out["rejects_stored"] = _rowcount(await self.conn.execute(REJECTS_INSERT, REJECT_CHECK))
        if flag_orphans:
            out.update(await self._flag(plan))
        return out

    async def _flag(self, plan: Plan) -> Counter:
        out: Counter = Counter()
        if plan.flag_trades:
            await self.conn.execute(ORPHAN_TRADES_DDL)
            await self.conn.copy_records_to_table(
                "stg_v1_orphan_trades", columns=["client_id", "fingerprint"],
                records=[(t["client_id"], t["fingerprint"]) for t in plan.flag_trades])
            out["trades_tombstoned"] = _rowcount(await self.conn.execute(ORPHAN_TRADES_FLAG))
        if plan.flag_clients:
            out["clients_inactivated"] = _rowcount(
                await self.conn.execute(ORPHAN_CLIENTS_FLAG, plan.flag_clients))
        if plan.flag_managers:
            out["managers_inactivated"] = _rowcount(
                await self.conn.execute(ORPHAN_MANAGERS_FLAG, plan.flag_managers))
        return out

    async def record_job(self, result: SyncResult, status: str, error: str | None = None) -> None:
        await self.conn.execute(
            "INSERT INTO ops.job_runs (job, finished_at, status, rows_in, rows_out, error, meta) "
            "VALUES ('v1_ledger_sync', now(), $1, $2, $3, $4, $5::jsonb)",
            status, len(result.plan["trades"].inserts), sum(result.applied.values()), error,
            json.dumps(result.as_dict(), default=str))


def _cell(v: Any) -> Any:
    return json.dumps(v, sort_keys=True) if isinstance(v, (dict, list)) else v


def _rowcount(status: Any) -> int:
    try:
        return int(str(status).rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0


def check_orphan_guard(plan: Plan, v2: V2Snapshot, max_fraction: float) -> None:
    v1_origin = sum(1 for t in v2.trades if t.get("v1_origin") and not t.get("deleted"))
    n = len(plan.flag_trades)
    if n and n > max(10, max_fraction * v1_origin):
        raise SyncAborted(
            f"refusing to tombstone {n} of {v1_origin} v1-origin trades (> {max_fraction:.0%}); "
            "check MONGODB_URL/MONGODB_DB, then rerun with a higher --max-orphan-fraction")


def check_source_sane(v1: V1Data) -> None:
    if not v1.managers or not v1.clients:
        raise SyncAborted("v1 returned no managers or clients: wrong MONGODB_DB? nothing written")


async def sync_with(
    conn: Any, v1: V1Data, *, dry_run: bool, flag_orphans: bool = False, today: date | None = None,
    cutover: datetime = DEFAULT_CUTOVER, max_orphan_fraction: float = MAX_ORPHAN_FRACTION,
) -> SyncResult:
    """Plan (and unless ``dry_run``, apply) against one connection. Injected for tests."""
    check_source_sane(v1)
    today = today or datetime.now(IST).date()
    repo = PgLedgerRepo(conn)
    tx = conn.transaction(readonly=True) if dry_run else conn.transaction()
    async with tx:
        if not dry_run and not await conn.fetchval(ADVISORY_LOCK):
            return SyncResult(dry_run, Plan(), skipped_locked=True)
        snap = await repo.snapshot(cutover)
        plan = plan_sync(v1, snap, today)
        result = SyncResult(dry_run, plan)
        if flag_orphans:
            check_orphan_guard(plan, snap, max_orphan_fraction)
        if dry_run:
            return result
        result.applied = await repo.apply(plan, flag_orphans)
        await repo.record_job(result, "OK")
    return result


async def run_sync(
    pg_dsn: str, mongo_url: str, *, mongo_db: str | None = None, dry_run: bool = True, **kw: Any,
) -> SyncResult:
    import asyncpg
    from pymongo import MongoClient  # local: only the sync job needs it

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000, socketTimeoutMS=300_000, tz_aware=False)
    try:
        mdb = client[mongo_db] if mongo_db else client.get_default_database(default="stocks")
        v1 = await asyncio.to_thread(read_v1, mdb)
    finally:
        client.close()
    conn = await asyncpg.connect(pg_dsn, timeout=15, command_timeout=600)
    try:
        await conn.execute("SET lock_timeout = '10s'")
        return await sync_with(conn, v1, dry_run=dry_run, **kw)
    finally:
        await conn.close()


def render(result: SyncResult) -> str:
    mode = "DRY-RUN (read-only transaction, nothing written)" if result.dry_run else "APPLIED"
    if result.skipped_locked:
        return "v1_ledger_sync: another run holds the lock; skipped"
    lines = [f"== v1_ledger_sync [{mode}] at {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
             f"{'entity':<20}{'insert':>8}{'update':>8}{'same':>8}{'orphan':>8}  notes"]
    for name, c in result.plan.counts().items():
        if name == "rejects":
            continue
        notes = {k: v for k, v in c.items() if k not in ("insert", "update", "unchanged", "orphan")}
        lines.append(f"{name:<20}{c['insert']:>8}{c['update']:>8}{c['unchanged']:>8}{c['orphan']:>8}  "
                     f"{notes or ''}")
    lines.append(f"rejects (entity:reason): {result.plan.counts()['rejects']}")
    for o in result.plan["clients"].orphans:
        lines.append(f"  ORPHAN client {o['client_id']} code={o['client_code']} active_trades={o['active_trades']}")
    for o in result.plan["managers"].orphans:
        lines.append(f"  ORPHAN manager {o['manager_id']}")
    by_client = Counter(str(t["client_id"]) for t in result.plan["trades"].orphans)
    for cid, n in sorted(by_client.items()):
        lines.append(f"  ORPHAN trades client={cid} n={n} (in v2, gone from v1)")
    lines.append(f"would flag: trades={len(result.plan.flag_trades)} clients={len(result.plan.flag_clients)} "
                 f"managers={len(result.plan.flag_managers)}  (only with --flag-orphans)")
    lines.append(f"changed clients={len(result.plan.changed_clients)} recompute_all={result.plan.recompute_all}")
    if result.applied:
        lines.append(f"applied: {dict(result.applied)}")
    return "\n".join(lines)
