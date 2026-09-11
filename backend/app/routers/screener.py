"""Swing-trade screener — a read-only, decision-support view over the sector universe.

Ranks every sector-covered stock on transparent technical metrics (short-term momentum,
relative strength vs its own sector, RSI, and traded volume) so a user can spot candidates
themselves. It intentionally makes NO buy/sell recommendation and computes no target price —
it surfaces the raw numbers and a transparent momentum score, and the user decides.

Data source: the same daily-close history + live quotes used everywhere else
(Angel One SmartAPI with Yahoo fallback), via app.services.market_data.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.routers.sectors import SECTORS_REGISTRY
from app.services.market_data import get_price_matrix, get_quote_details
from app.services.stock_news import get_stock_news

log = logging.getLogger("screener")

router = APIRouter(prefix="/api/screener", tags=["screener"])


def _name_for_ticker(ticker: str) -> str | None:
    t = ticker.upper()
    for sec in SECTORS_REGISTRY.values():
        for c in sec["covered"] + sec["roster"]:
            if c["ticker"].upper() == t:
                return c["name"]
    # Fall back to the broad Nifty-500 universe (for the news lookup on 500 stocks).
    try:
        from app.services import screener_daily
        rec = screener_daily._load_kpis().get(t)
        if rec:
            return rec.get("name")
    except Exception:
        pass
    return None


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else None


def _fundamentals(company: dict, sector_id: str) -> dict:
    """Normalise the hand-researched quarterly + fundamental fields (which differ per sector
    schema) into one common shape for the 'what to watch' briefing. Covered names carry these;
    roster names return has_results=False. Pure fact passthrough — no scoring, no advice."""
    f = {
        "has_results": False,
        "market_cap_cr": company.get("market_cap_cr"),
        "pe_label": company.get("pe_label"),
        "pat_yoy_pct": company.get("pat_yoy_pct"),
        "pat_yoy_label": company.get("pat_yoy_label"),
        "rev_growth_label": None, "rev_growth_pct": None,
        "margin_label": None, "margin_pct": None,
        "quality_label": None, "quality_value": None, "quality_status": None,
        "note": company.get("note"),
    }
    # Revenue growth (banks report NII instead of revenue).
    if sector_id == "banks":
        f["rev_growth_label"], f["rev_growth_pct"] = "NII YoY", company.get("nii_yoy_pct")
        f["margin_label"], f["margin_pct"] = "NIM", company.get("nim_pct")
        f["quality_label"], f["quality_value"] = "GNPA", company.get("gnpa_pct")
    elif sector_id == "it":
        f["rev_growth_label"], f["rev_growth_pct"] = "Revenue YoY", company.get("revenue_yoy_pct")
        f["margin_label"], f["margin_pct"] = "EBIT margin", company.get("ebit_margin_pct")
    else:  # hotels, auto
        f["rev_growth_label"], f["rev_growth_pct"] = "Revenue YoY", company.get("revenue_yoy_pct")
        f["margin_label"], f["margin_pct"] = "EBITDA margin", company.get("ebitda_margin_pct")
        f["quality_label"] = "Leverage"
        f["quality_value"] = company.get("leverage_label")
        f["quality_status"] = company.get("leverage_status")

    # "Has results" = we actually researched a P&L for this name (covered, not roster-only).
    if any(f[k] is not None for k in ("pat_yoy_pct", "rev_growth_pct", "margin_pct")):
        f["has_results"] = True
    return f


# ── Snapshot cache ────────────────────────────────────────────────────────────────
# The full compute fetches ~1 year of history for the whole covered universe (160+ symbols),
# paced by Angel's ~3 candle-calls/sec limit → ~1 minute cold. That must NEVER run inline on
# the event loop (it froze the whole backend). Instead we compute it in a worker thread,
# cache the result, and serve the cached snapshot immediately — refreshing in the background
# when stale (stale-while-revalidate), with an asyncio lock for single-flight so concurrent
# misses share one refresh instead of each launching its own fetch storm.
_SNAPSHOT: dict = {"data": None, "computed_at": 0.0}
_SNAPSHOT_TTL = 600.0          # serve cached for 10 min, then refresh in the background
_refresh_lock = asyncio.Lock()


def _compute_screener() -> dict:
    """The heavy synchronous compute — runs in a worker thread (asyncio.to_thread), never
    on the event loop. Now the BROAD Nifty-500 screen: momentum/RSI/levels/ATR read from the
    Mongo daily store (zero Angel calls) + FY26 fundamentals from nifty500_kpis.json.
    See app.services.screener_daily. The curated 10-sector data still powers the /sectors
    (R&D) page and the per-stock news lookup below."""
    from app.services import screener_daily
    return screener_daily.compute()


async def _ensure_snapshot_fresh() -> None:
    """Recompute the snapshot off the event loop, single-flight. A caller that finds the
    lock held waits for the in-flight refresh rather than launching its own fetch storm."""
    async with _refresh_lock:
        # Someone may have refreshed while we waited for the lock.
        if _SNAPSHOT["data"] is not None and (time.time() - _SNAPSHOT["computed_at"]) < _SNAPSHOT_TTL:
            return
        data = await asyncio.to_thread(_compute_screener)
        _SNAPSHOT["data"] = data
        _SNAPSHOT["computed_at"] = time.time()


async def warm_screener() -> None:
    """Pre-warm the snapshot at startup so the first user never pays the cold cost.
    Never raises into startup."""
    try:
        await _ensure_snapshot_fresh()
        log.info("screener snapshot pre-warmed: %d stocks", (_SNAPSHOT["data"] or {}).get("count", 0))
    except Exception:
        log.exception("screener pre-warm failed (will compute lazily on first request)")


@router.get("")
async def screener():
    """Ranked technical snapshot across all covered sectors.

    Served from a background-refreshed snapshot (stale-while-revalidate): the heavy
    ~1-minute fetch runs in a worker thread and never blocks the event loop. Returns each
    stock's momentum (1D/1W/1M/1Y), RSI(14), volume, distance-from-52w-high, relative
    strength, a transparent composite score, plus per-sector averages. No advice.
    """
    snap = _SNAPSHOT
    age = time.time() - snap["computed_at"]
    if snap["data"] is not None and age < _SNAPSHOT_TTL:
        return {"data": snap["data"]}                              # fresh — instant
    if snap["data"] is not None:
        asyncio.create_task(_ensure_snapshot_fresh())             # stale — refresh in bg
        return {"data": {**snap["data"], "stale": True}}          # serve stale immediately
    # Cold start: compute once, off-loop + single-flight. The event loop stays responsive
    # for every other endpoint while this runs.
    await _ensure_snapshot_fresh()
    data = _SNAPSHOT["data"] or {
        "generated_at": None, "count": 0, "stocks": [], "sectors": {}, "warming": True,
    }
    return {"data": data}


@router.get("/news/{ticker}")
async def stock_news(ticker: str):
    """Recent news headlines for one covered stock (Google News RSS, cached).

    Context only: returns headline + source + date + link (+ factual keyword tags found in
    the headline). It does NOT claim why a stock moved — the user reads the headlines and
    judges. 404 only if the ticker isn't in the covered universe.
    """
    name = _name_for_ticker(ticker)
    if not name:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not in covered universe")
    return {"data": get_stock_news(name, ticker.upper())}
