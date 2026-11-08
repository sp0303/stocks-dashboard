"""Daily sync of v1's screener output into research.screener_snapshots (model 'v1_daily').

v1 ranks the Nifty-500 by the validated Phase-1 composite and adds the setup label, the
trade-plan hold, per-stock 1D/1W/1M/1Y, sector (NSE industry), event badges and a market
context block (regime, F&O expiry phase). v2 serves that screen read-only until the
screener itself is ported; this job copies it across once a day after v1's snapshot.

Sources, both READ-ONLY on v1:
  * ``api``   - v1's ``GET /api/screener`` (``V1_SCREENER_URL``): the full payload. Only the
                v1 process can compute it (it owns the factor code and FY26 KPI file).
  * ``mongo`` - v1's Phase-5 ``screener_snapshots`` collection: a thin record (score, setup,
                plan entry/stop/target) with no price, returns, sector or badges. Used only
                when the API is unavailable, and never overwrites a full snapshot.
``auto`` (default) tries ``api`` then ``mongo``.

Writes are one upsert keyed on (as_of, model): re-running is idempotent. ``--dry-run``
executes the statement inside a transaction and rolls back. Logs counts only.
Run: ``python -m pi_workers.v1_sync_screener [--source auto|api|mongo] [--dry-run]``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger("pi_workers.v1_sync_screener")

MODEL = "v1_daily"
SOURCE_API = "v1_api"
SOURCE_MONGO = "v1_mongo_snapshot"
MIN_STOCKS = 50  # a v1 screen that is still warming (or broken) must not replace a good one
HTTP_TIMEOUT_S = 180  # a cold v1 compute takes ~1 minute
MONGO_COLL = "screener_snapshots"

UPSERT_SQL = """
INSERT INTO research.screener_snapshots (as_of, model, payload)
VALUES ($1, $2, $3::jsonb)
ON CONFLICT (as_of, model) DO UPDATE SET payload = EXCLUDED.payload
WHERE research.screener_snapshots.payload IS DISTINCT FROM EXCLUDED.payload
  AND NOT (research.screener_snapshots.payload->>'source' = 'v1_api'
           AND EXCLUDED.payload->>'source' IS DISTINCT FROM 'v1_api')
"""


class SyncRefused(Exception):
    """The source payload is not fit to publish (empty, warming, undated)."""


class _DryRunRollback(Exception):
    pass


# ── pure transforms (unit-tested) ─────────────────────────────────────────────
def clean_json(v: Any) -> Any:
    """NaN/inf are not valid JSON(B): store them as null (unknown, never 0 - R15 spirit)."""
    if isinstance(v, float) and not math.isfinite(v):
        return None
    if isinstance(v, dict):
        return {str(k): clean_json(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean_json(x) for x in v]
    return v


def parse_as_of(value: Any) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as exc:
        raise SyncRefused(f"undated payload: {value!r}") from exc


def payload_from_api(body: Any, synced_at: str) -> tuple[date, dict[str, Any]]:
    """v1 returns ``{"data": {...}}``; keep every field (lossless) and tag units + source."""
    data = body.get("data") if isinstance(body, dict) and "data" in body else body
    if not isinstance(data, dict) or data.get("warming"):
        raise SyncRefused("v1 screener is warming / returned no data")
    stocks = data.get("stocks")
    if not isinstance(stocks, list) or len(stocks) < MIN_STOCKS:
        raise SyncRefused(f"v1 screener returned {len(stocks or [])} stocks (< {MIN_STOCKS})")
    as_of = parse_as_of(data.get("data_as_of"))
    payload = {**data, "units": "percent", "source": SOURCE_API, "synced_at": synced_at,
               "v1_served_stale": bool(data.get("stale"))}
    payload.pop("stale", None)
    return as_of, payload


def payload_from_mongo(doc: Any, synced_at: str) -> tuple[date, dict[str, Any]]:
    """Thin Phase-5 snapshot -> the same payload shape, ranked by the stored composite score."""
    if not isinstance(doc, dict):
        raise SyncRefused("no v1 Mongo snapshot")
    as_of = parse_as_of(doc.get("data_as_of") or doc.get("as_of") or doc.get("_id"))
    src = [s for s in doc.get("stocks") or [] if isinstance(s, dict) and s.get("ticker")]
    if len(src) < MIN_STOCKS:
        raise SyncRefused(f"v1 Mongo snapshot has {len(src)} stocks (< {MIN_STOCKS})")
    src.sort(key=lambda s: (s.get("score") is not None, s.get("score") or 0), reverse=True)
    stocks = [
        {
            "ticker": str(s["ticker"]).upper(), "rank": i, "score": s.get("score"),
            "setup": s.get("setup"), "value_score": s.get("value_score"),
            "quality_score": s.get("quality_score"),
            "plan": {"entry": s.get("entry"), "stop": s.get("stop"), "t2": s.get("t2")},
        }
        for i, s in enumerate(src, 1)
    ]
    payload = {"data_as_of": as_of.isoformat(), "generated_at": doc.get("created_at"),
               "count": len(stocks), "stocks": stocks, "market": None, "units": "percent",
               "source": SOURCE_MONGO, "synced_at": synced_at}
    return as_of, payload


# ── I/O ───────────────────────────────────────────────────────────────────────
def fetch_api(url: str, timeout: float = HTTP_TIMEOUT_S) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if resp.status != 200:
            raise SyncRefused(f"v1 screener HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def fetch_mongo_latest(mongo_url: str, mongo_db: str | None) -> Any:
    from pymongo import MongoClient  # local import: only this job needs it

    client = MongoClient(mongo_url, serverSelectionTimeoutMS=10_000, socketTimeoutMS=60_000)
    try:
        db = client[mongo_db] if mongo_db else client.get_default_database(default="stocks")
        return db[MONGO_COLL].find_one({}, sort=[("_id", -1)])  # read-only
    finally:
        client.close()


def load_source(source: str, env: dict[str, str], synced_at: str) -> tuple[date, dict[str, Any]]:
    errors: list[str] = []
    if source in ("auto", "api"):
        url = env.get("V1_SCREENER_URL")
        try:
            if not url:
                raise SyncRefused("V1_SCREENER_URL is not set")
            return payload_from_api(fetch_api(url), synced_at)
        except Exception as exc:  # network/HTTP/shape: fall through in auto mode
            errors.append(f"api: {type(exc).__name__}: {exc}")
            if source == "api":
                raise
    mongo_url = env.get("MONGODB_URL")
    if not mongo_url:
        raise SyncRefused("; ".join(errors + ["mongo: MONGODB_URL is not set"]))
    try:
        return payload_from_mongo(fetch_mongo_latest(mongo_url, env.get("MONGODB_DB")), synced_at)
    except Exception as exc:
        raise SyncRefused("; ".join(errors + [f"mongo: {type(exc).__name__}: {exc}"])) from exc


async def write_snapshot(conn: Any, as_of: date, payload: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    """Idempotent upsert in one transaction; dry-run rolls it back after executing."""
    report: dict[str, Any] = {"as_of": as_of.isoformat(), "model": MODEL, "dry_run": dry_run,
                              "source": payload["source"], "stocks": len(payload["stocks"])}
    try:
        async with conn.transaction():
            body = json.dumps(clean_json(payload), default=str, allow_nan=False)
            status = await conn.execute(UPSERT_SQL, as_of, MODEL, body)
            report["written"] = status.endswith(" 1")
            if dry_run:
                raise _DryRunRollback()
            await conn.execute(
                "INSERT INTO ops.job_runs (job, finished_at, status, rows_in, rows_out, meta) "
                "VALUES ('v1_screener_sync', now(), 'OK', $1, $2, $3::jsonb)",
                report["stocks"], 1 if report["written"] else 0, json.dumps(report),
            )
    except _DryRunRollback:
        logger.info("dry-run: transaction rolled back")
    return report


async def run(source: str, dry_run: bool, env: dict[str, str] | None = None) -> dict[str, Any]:
    import asyncpg

    env = dict(os.environ if env is None else env)
    dsn = env.get("PG_DSN") or env.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL (or PG_DSN) is not set")
    synced_at = datetime.now(timezone.utc).isoformat()
    as_of, payload = await asyncio.to_thread(load_source, source, env, synced_at)
    conn = await asyncpg.connect(dsn, command_timeout=120, timeout=15)
    try:
        return await write_snapshot(conn, as_of, payload, dry_run)
    finally:
        await conn.close()


def _cli(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source", choices=("auto", "api", "mongo"), default="auto")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    try:
        report = asyncio.run(run(args.source, args.dry_run))
    except SyncRefused as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 2
    print(json.dumps(report, default=str, sort_keys=True))  # counts only
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
