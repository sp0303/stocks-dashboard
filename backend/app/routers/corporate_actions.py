"""Corporate-actions routes: fetch/refresh splits, bonuses, demergers etc. from NSE.

Two scopes (as chosen for this project):
  * POST /refresh      — portfolio-scoped: every symbol/ISIN actually held across all
                         clients. Fast, reliable, and all of it is used by the engine.
  * POST /refresh-all  — market-wide backfill from the full NSE equity list, run as a
                         background task with incremental saves (thousands of symbols).

Network fetches are blocking (httpx + polite pacing), so they run in a worker thread to
keep the event loop free.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Query
from fastapi.concurrency import run_in_threadpool

from app.services import corporate_actions as ca
from app.store import get_store

log = logging.getLogger("corporate_actions")
router = APIRouter(prefix="/api/corporate-actions", tags=["corporate-actions"])

_backfill = {"running": False, "done": 0, "total": 0, "saved": 0}


async def _held_symbols() -> tuple[list[str], list[str]]:
    """Distinct (symbols, isins) across every client's trades."""
    store = get_store()
    symbols: set[str] = set()
    isins: set[str] = set()
    for c in await store.list_clients():
        for t in await store.list_trades(c["id"]):
            if t.get("symbol"):
                symbols.add(t["symbol"].upper())
            if t.get("isin"):
                isins.add(t["isin"])
    return sorted(symbols), sorted(isins)


@router.get("")
async def list_actions(symbol: str | None = None, isin: str | None = None):
    rows = await get_store().list_corporate_actions(
        [isin] if isin else None, [symbol] if symbol else None
    )
    rows.sort(key=lambda r: (r.get("symbol") or "", r.get("ex_date") or ""))
    return {"data": rows}


@router.get("/coverage")
async def coverage():
    cov = await get_store().corporate_actions_coverage()
    return {"data": {**cov, "backfill": _backfill}}


@router.post("/refresh")
async def refresh(from_date: str = Query("01-01-2020")):
    """Fetch corporate actions for all held symbols and persist them."""
    symbols, _isins = await _held_symbols()
    if not symbols:
        return {"data": {"symbols": 0, "fetched": 0, "saved": 0}}
    records = await run_in_threadpool(ca.fetch_for_symbols, symbols, from_date)
    saved = await get_store().save_corporate_actions(records)
    return {"data": {"symbols": len(symbols), "fetched": len(records), "saved": saved}}


async def _run_backfill(from_date: str) -> None:
    """Market-wide backfill. Blocking NSE fetches run in worker threads; store writes stay
    on the event loop (motor-safe). Persists per symbol so an interrupted run isn't lost."""
    import asyncio

    store = get_store()
    symbols = await run_in_threadpool(ca.fetch_all_nse_symbols)
    if not symbols:
        log.warning("backfill: could not load NSE symbol list; aborting")
        _backfill.update(running=False)
        return
    _backfill.update(running=True, done=0, total=len(symbols), saved=0)
    client = await run_in_threadpool(ca._client)
    try:
        for sym in symbols:
            recs = await run_in_threadpool(ca.fetch_nse_symbol, sym, from_date, None, client)
            _backfill["done"] += 1
            if recs:
                _backfill["saved"] += await store.save_corporate_actions(recs)
            await asyncio.sleep(0.3)  # polite pacing
    finally:
        await run_in_threadpool(client.close)
        _backfill["running"] = False
        log.info("backfill complete: %s symbols, %s actions saved",
                 _backfill["done"], _backfill["saved"])


@router.post("/refresh-all")
async def refresh_all(background: BackgroundTasks, from_date: str = Query("01-01-2020")):
    """Kick off the market-wide backfill in the background. Poll /coverage for progress."""
    if _backfill["running"]:
        return {"data": {"status": "already-running", **_backfill}}
    background.add_task(_run_backfill, from_date)
    return {"data": {"status": "started"}}
