"""Portfolio analytics routes (read-only, derived)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

import asyncio
import hashlib
import uuid

from app.models.schemas import (
    DividendCreate, DividendUpdate, ManualTradeCreate, TagCreate, TagUpdate, TradeNoteUpdate, TradeTagsUpdate,
)
from app.services import analytics
from app.services.engine import compute_positions, split_intraday
from app.services.llm import fallback_narrate, narrate
from app.services.market_data import get_dividend_history
from app.store import get_store

router = APIRouter(prefix="/api/clients", tags=["portfolio"])

BENCHMARK_SYMBOL = "^NSEI"

# Real NSE index tickers backing the Performance chart's benchmark comparison — each
# verified to return live Yahoo chart data. "Large Cap" is Nifty 100 (broader than the
# Nifty 50 line itself, matching what the UI's checkbox implies).
BENCHMARK_INDEX_SYMBOLS = {
    "nifty_50": "^NSEI",
    "mid_cap": "^CRSMID",
    "large_cap": "^CNX100",
    # ^CNXSC (Nifty Smallcap 100) only exposes ~1 day of history on Yahoo's chart
    # endpoint — verified dead end. NIFTYSMLCAP250.NS is the same index family under its
    # .NS-suffixed ticker and does carry a real daily history there.
    "small_cap": "NIFTYSMLCAP250.NS",
}


async def _benchmark_price_map(trades: list[dict], symbol: str = BENCHMARK_SYMBOL) -> dict[str, float]:
    """Cached-first index close series covering the client's trading history. Only the
    dates missing from the store's `benchmark_prices` cache (keyed per symbol) are
    fetched from Yahoo."""
    if not trades:
        return {}
    store = get_store()
    cached = await store.get_benchmark_prices(symbol)
    first_trade_date = min(t["trade_date"] for t in trades)
    today = date.today().strftime("%Y-%m-%d")

    have_recent = cached and max(cached.keys()) >= (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    if cached and have_recent and min(cached.keys()) <= first_trade_date:
        return cached

    # Index tickers (^XXXX) don't take the NSE/.NS suffix rewrite that get_history applies
    # to equities, so fetch the raw ticker directly.
    fetched = _fetch_index_history(symbol, first_trade_date, today)
    new_prices = {p["date"]: p["close"] for p in fetched}
    if new_prices:
        await store.save_benchmark_prices(symbol, new_prices)
    merged = {**cached, **new_prices}
    return merged


def _fetch_index_history(symbol: str, from_date: str, to_date: str) -> list[dict]:
    """Index tickers (^XXXX) need the raw Yahoo ticker (no .NS/.BO suffix), so this
    bypasses market_data.get_history's equity-ticker rewriting and hits the chart
    endpoint directly."""
    import time as _time
    from datetime import datetime, timezone

    import httpx

    from app.services.market_data import _CHART_HOSTS

    try:
        p1 = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    except ValueError:
        p1 = int(_time.time()) - 365 * 86400
    p2 = int(_time.time())

    for host in _CHART_HOSTS:
        url = f"{host}/v8/finance/chart/{symbol}?period1={p1}&period2={p2}&interval=1d"
        try:
            r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12.0)
            if r.status_code != 200:
                continue
            res = r.json()["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0].get("close", [])
            return [
                {"date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), "close": round(float(c), 2)}
                for t, c in zip(ts, closes) if c is not None
            ]
        except Exception:
            continue
    return []


async def _raw_trades_or_404(client_id: str) -> list[dict]:
    """Every stored trade, unfiltered — same-day intraday round trips included. Only for
    endpoints that must show the literal trade ledger (the Trades tab, manual-trade
    listing), not derived analysis."""
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return await store.list_trades(client_id)


async def _trades_or_404(client_id: str) -> list[dict]:
    """Delivery/swing trades only — same-day round trips (intraday/speculative, per
    Section 43(5)) are split out by engine.split_intraday() so they don't pollute avg
    cost, holding days, playbook, and performance stats built on top of this. This is
    what every holdings/analysis endpoint should use; see _raw_trades_or_404 for the
    unfiltered ledger and _delivery_and_intraday() when the intraday side is also needed
    (e.g. to report intraday P&L separately)."""
    delivery, _ = await _delivery_and_intraday(client_id)
    return delivery


async def _delivery_and_intraday(client_id: str) -> tuple[list[dict], list[dict]]:
    trades = await _raw_trades_or_404(client_id)
    return split_intraday(trades)


async def _client_or_404(client_id: str) -> dict:
    store = get_store()
    client = await store.get_client(client_id)
    if not client:
        raise HTTPException(404, "client not found")
    return client


async def _actions_for(trades: list[dict]) -> list[dict]:
    """Corporate actions (splits/bonuses) relevant to these trades, so the FIFO engine can
    keep held quantities correct across a split/bonus. Empty until a CA refresh is run."""
    if not trades:
        return []
    isins = {t.get("isin") for t in trades if t.get("isin")}
    symbols = {t.get("symbol") for t in trades if t.get("symbol")}
    return await get_store().list_corporate_actions(list(isins), list(symbols))


@router.get("/{client_id}/portfolio")
async def portfolio(client_id: str):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.portfolio_summary(trades, await _actions_for(trades))}


@router.get("/{client_id}/holdings")
async def holdings(client_id: str):
    trades = await _trades_or_404(client_id)
    data = analytics.build_holdings(trades, actions=await _actions_for(trades))
    data.pop("_positions", None)
    return {"data": data}


@router.get("/{client_id}/corporate-actions")
async def client_corporate_actions(client_id: str):
    """Corporate actions (split/bonus/demerger/buyback/dividend) for every security this
    client has traded — the portfolio-level CA feed. Newest first."""
    trades = await _trades_or_404(client_id)
    actions = await _actions_for(trades)
    actions.sort(key=lambda a: (a.get("ex_date") or ""), reverse=True)
    return {"data": actions}


@router.post("/{client_id}/corporate-actions/refresh")
async def client_corporate_actions_refresh(client_id: str):
    """Fetch corporate actions from NSE for just this client's held symbols and persist."""
    from fastapi.concurrency import run_in_threadpool
    from app.services import corporate_actions as ca

    trades = await _trades_or_404(client_id)
    symbols = sorted({t["symbol"].upper() for t in trades if t.get("symbol")})
    if not symbols:
        return {"data": {"symbols": 0, "fetched": 0, "saved": 0}}
    records = await run_in_threadpool(ca.fetch_for_symbols, symbols, "01-01-2020")
    saved = await get_store().save_corporate_actions(records)
    return {"data": {"symbols": len(symbols), "fetched": len(records), "saved": saved}}


@router.get("/{client_id}/allocation")
async def allocation(
    client_id: str,
    by: str = Query("sector", pattern="^(sector|asset|stock|cap)$"),
    basis: str = Query("current", pattern="^(current|invested)$"),
):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.allocation(trades, by, basis)}


@router.get("/{client_id}/concentration")
async def concentration(client_id: str):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.concentration(trades)}


_perf_series_cache: dict[str, tuple[list[dict], float]] = {}
_PERF_SERIES_TTL = 900   # 15 min; the curve only moves once a day + on a new trade


def _perf_cache_key(client_id: str, trades: list[dict]) -> str:
    """Invalidate when trades change: count + latest trade date is enough — an upload
    always adds rows or moves the max date."""
    last = max((t["trade_date"] for t in trades), default="")
    return f"{client_id}:{len(trades)}:{last}"


async def cached_performance_series(client_id: str, trades: list[dict],
                                    actions: list[dict]) -> list[dict]:
    """compute_performance_series is O(trades^2) (it re-derives positions for every
    trade-day) and gets called for every client on every manager-page poll. The curve
    changes at most once a day, so memoise it per client and let the poll storm hit the
    cache instead of the CPU."""
    import time as _t
    key = _perf_cache_key(client_id, trades)
    hit = _perf_series_cache.get(key)
    if hit and _t.time() - hit[1] < _PERF_SERIES_TTL:
        return hit[0]
    series = await compute_performance_series(trades, actions)
    _perf_series_cache[key] = (series, _t.time())
    return series


async def warm_performance_cache() -> None:
    """Pre-compute every client's performance series into the cache at startup, off the
    request path, so the first manager/client page load doesn't pay the O(trades^2) cold
    cost. Never raises into startup."""
    import logging
    log = logging.getLogger("perf.warm")
    try:
        store = get_store()
        clients = await store.list_clients()          # None manager_id = all clients
    except Exception as exc:
        log.warning("performance warm skipped: %s", exc)
        return
    done = 0
    for c in clients:
        try:
            trades = await store.list_trades(c["id"])
            if not trades:
                continue
            actions = await _actions_for(trades)
            await cached_performance_series(c["id"], trades, actions)
            await cached_trade_analytics(c["id"], trades)
            done += 1
        except Exception as exc:
            log.warning("performance warm %s: %s", c.get("id"), exc)
    log.info("performance cache warmed for %d clients", done)


async def compute_performance_series(trades: list[dict], actions: list[dict]) -> list[dict]:
    """Portfolio value over time (marked to market with real historical prices, not just
    cost basis) plus, for each benchmark index, what the SAME buy/sell cash flows would be
    worth today had they gone into that index instead. Both sides are real value curves
    computed from real prices on the same dates — a true apples-to-apples comparison.
    Shared by the single-client /performance route and the manager-level book/individual
    comparison endpoint, so both use identical, real (non-mocked) methodology."""
    from app.services import market_data

    series = analytics.performance_series(trades)
    if not trades:
        return series

    # Mark the portfolio's own line to market: fetch each traded symbol's historical
    # close series and revalue open positions day-by-day, instead of the cost-basis
    # fallback already in `series` (which silently omits unrealized gains/losses).
    exchange_by_symbol = {t["symbol"]: t.get("exchange") or "NSE" for t in trades}
    first_trade_date = min((t["trade_date"] for t in trades), default=None)
    if first_trade_date:
        symbols = sorted(exchange_by_symbol)

        async def _history_for(sym: str) -> tuple[str, dict[str, float]]:
            result = await run_in_threadpool(
                market_data.get_history, sym, first_trade_date, "1d", exchange_by_symbol[sym]
            )
            return sym, {p["date"]: p["close"] for p in result.get("points", [])}

        histories = await asyncio.gather(*(_history_for(s) for s in symbols))
        price_maps = {sym: prices for sym, prices in histories if prices}
        if price_maps:
            mtm = {row["date"]: row["market_value"] for row in analytics.market_value_series(trades, price_maps, actions)}
            for row in series:
                if row["date"] in mtm:
                    row["total_value"] = mtm[row["date"]]

    for key, symbol in BENCHMARK_INDEX_SYMBOLS.items():
        prices = await _benchmark_price_map(trades, symbol)
        if not prices:
            continue
        bench = {row["date"]: row["benchmark_value"] for row in analytics.benchmark_series(trades, prices)}
        for row in series:
            row[f"{key}_value"] = bench.get(row["date"])

    return series


@router.get("/{client_id}/performance")
async def performance(client_id: str):
    trades = await _trades_or_404(client_id)
    actions = await _actions_for(trades)
    series = await cached_performance_series(client_id, trades, actions)
    return {"data": series}


@router.get("/{client_id}/metrics")
async def metrics(client_id: str, response: Response):
    """Phase 1: Core performance metrics (CAGR, Sharpe, volatility, drawdown, beta, alpha).
    Compares portfolio against Nifty 50 benchmark. Cache for 5 minutes."""
    # Add cache headers to reduce redundant calculations on client-side
    response.headers["Cache-Control"] = "public, max-age=300"

    trades = await _trades_or_404(client_id)
    actions = await _actions_for(trades)

    # Get portfolio performance series
    performance_series = await compute_performance_series(trades, actions)

    # Override the last row with current market data from holdings
    if performance_series:
        holdings_data = analytics.build_holdings(trades, with_prices=True, actions=actions or [])
        current_invested = holdings_data["totals"]["invested_value"]
        current_market_value = holdings_data["totals"]["market_value"]
        current_unrealized = holdings_data["totals"]["unrealized_pnl"]

        # Get realized P&L (constant, from closed trades)
        _, realized = analytics.compute_positions(trades, actions=actions or [])

        current_total_pnl = current_unrealized + realized
        current_total_value = current_invested + current_total_pnl

        # Update or append today's row with real current values
        from datetime import date
        today_str = str(date.today())
        today_row_idx = -1
        for i, row in enumerate(performance_series):
            if row["date"] == today_str:
                today_row_idx = i
                break

        if today_row_idx >= 0:
            # Update existing today row
            performance_series[today_row_idx]["invested_value"] = round(current_invested, 2)
            performance_series[today_row_idx]["realized_pnl"] = round(realized, 2)
            performance_series[today_row_idx]["total_value"] = round(current_total_value, 2)
            performance_series[today_row_idx]["portfolio_return"] = round(
                (current_total_value / (performance_series[0]["invested_value"] if performance_series[0]["invested_value"] > 0 else 1)) * 100, 2
            )
        elif performance_series[-1]["date"] != today_str:
            # Append new today row
            performance_series.append({
                "date": today_str,
                "invested_value": round(current_invested, 2),
                "realized_pnl": round(realized, 2),
                "total_value": round(current_total_value, 2),
                "portfolio_return": round(
                    (current_total_value / (performance_series[0]["invested_value"] if performance_series[0]["invested_value"] > 0 else 1)) * 100, 2
                ),
            })

    # Extract benchmark series (Nifty 50 for comparison)
    nifty_series = None
    if performance_series:
        nifty_series = [
            {"date": row["date"], "total_value": row.get("nifty_50_value")}
            for row in performance_series
            if row.get("nifty_50_value") is not None
        ]

    # Calculate all Phase 1 metrics
    metrics_data = analytics.compute_performance_metrics(
        performance_series,
        benchmark_performance=nifty_series,
        risk_free_rate=0.065  # Current RBI repo rate
    )

    return {"data": metrics_data}


@router.get("/{client_id}/attribution")
async def attribution(client_id: str, response: Response):
    """Phase 2: Performance attribution (sector vs stock selection breakdown).
    Shows where returns came from: sector timing vs picking good stocks within sectors.
    Cache for 5 minutes."""
    # Add cache headers
    response.headers["Cache-Control"] = "public, max-age=300"

    trades = await _trades_or_404(client_id)
    actions = await _actions_for(trades)
    performance_series = await compute_performance_series(trades, actions)

    # Calculate all Phase 2 attribution metrics
    attribution_data = analytics.compute_attribution_metrics(
        performance_series,
        trades
    )

    return {"data": attribution_data}


_ta_cache: dict[str, tuple[dict, float]] = {}
_TA_TTL = 900


async def cached_trade_analytics(client_id: str, trades: list[dict]) -> dict:
    """compute_trade_analytics resolves a sector per distinct symbol (a possible network
    lookup) and matches every round trip — heavy for a big book, and the section polls.
    Memoise per client, invalidated by trade count + last trade date."""
    import time as _t
    last = max((t["trade_date"] for t in trades), default="")
    key = f"{client_id}:{len(trades)}:{last}"
    hit = _ta_cache.get(key)
    if hit and _t.time() - hit[1] < _TA_TTL:
        return hit[0]
    data = await run_in_threadpool(analytics.compute_trade_analytics, trades)
    _ta_cache[key] = (data, _t.time())
    return data


@router.get("/{client_id}/trade-analytics")
async def trade_analytics(client_id: str):
    """Phase 3: Trade quality metrics (win rate, profit factor, best/worst trades)."""
    trades = await _trades_or_404(client_id)
    return {"data": await cached_trade_analytics(client_id, trades)}


@router.get("/{client_id}/risk-monitoring")
async def risk_monitoring(client_id: str):
    """Phase 4: Risk monitoring (concentration, health score, alerts)."""
    trades = await _trades_or_404(client_id)
    actions = await _actions_for(trades)
    performance_series = await compute_performance_series(trades, actions)
    risk_data = analytics.compute_risk_monitoring(performance_series, trades)
    return {"data": risk_data}


@router.get("/{client_id}/xirr")
async def xirr(client_id: str):
    store = get_store()
    trades = await _trades_or_404(client_id)
    dividends = await store.list_dividends(client_id)
    return {"data": {"xirr": analytics.portfolio_xirr(trades, dividends), "cagr": analytics.cagr(trades)}}


@router.get("/{client_id}/trades")
async def trades(
    client_id: str,
    symbol: str | None = None,
    trade_type: str | None = None,
    tag: str | None = None,
):
    """Raw trade ledger — every buy/sell including same-day intraday round trips."""
    store = get_store()
    ts = await _raw_trades_or_404(client_id)
    if symbol:
        ts = [t for t in ts if t["symbol"] == symbol.upper()]
    if trade_type:
        ts = [t for t in ts if t["trade_type"] == trade_type.lower()]
    ts.sort(key=lambda t: (t["trade_date"], t.get("order_execution_time", "")), reverse=True)
    journal = await store.get_trade_journal(client_id)
    for t in ts:
        j = journal.get(t["fingerprint"], {})
        t["tag_ids"] = j.get("tag_ids", [])
        t["note"] = j.get("note", "")
    if tag:
        ts = [t for t in ts if tag in t["tag_ids"]]
    return {"data": ts, "meta": {"total": len(ts)}}


@router.get("/{client_id}/tags")
async def list_tags(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.list_tags(client_id)}


@router.post("/{client_id}/tags")
async def create_tag(client_id: str, body: TagCreate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    doc = {**body.model_dump(), "client_id": client_id}
    return {"data": await store.create_tag(doc)}


@router.patch("/{client_id}/tags/{tag_id}")
async def update_tag(client_id: str, tag_id: str, body: TagUpdate):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await store.update_tag(client_id, tag_id, patch)
    if not updated:
        raise HTTPException(404, "tag not found")
    return {"data": updated}


@router.delete("/{client_id}/tags/{tag_id}")
async def delete_tag(client_id: str, tag_id: str):
    store = get_store()
    ok = await store.delete_tag(client_id, tag_id)
    if not ok:
        raise HTTPException(404, "tag not found")
    return {"data": {"deleted": True}}


@router.patch("/{client_id}/trades/{fingerprint}/tags")
async def set_trade_tags(client_id: str, fingerprint: str, body: TradeTagsUpdate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.set_trade_tags(client_id, fingerprint, body.tag_ids)}


@router.patch("/{client_id}/trades/{fingerprint}/note")
async def set_trade_note(client_id: str, fingerprint: str, body: TradeNoteUpdate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.set_trade_note(client_id, fingerprint, body.note)}


@router.get("/{client_id}/playbook")
async def playbook(
    client_id: str,
    symbol: str | None = None,
    sort: str = Query(
        "sell_date",
        pattern="^(sell_date|buy_date|days|pnl|pnl_pct|symbol|quantity|buy_price|sell_price|reason)$",
    ),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    store = get_store()
    ts = await _trades_or_404(client_id)
    journal = await store.get_trade_journal(client_id)
    tags = await store.list_tags(client_id)
    rows = analytics.playbook(ts, journal, tags)
    if symbol:
        rows = [r for r in rows if r["symbol"] == symbol.upper()]
    rows.sort(key=lambda r: r[sort] if r[sort] is not None else 0, reverse=(order == "desc"))
    rows.sort(key=lambda r: r[sort] is None)  # None always last, regardless of order (stable sort)
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start : start + page_size]
    return {
        "data": page_rows,
        "meta": {"total": total, "page": page, "page_size": page_size, "pages": max(1, -(-total // page_size))},
    }


@router.get("/{client_id}/playbook/by-stock")
async def playbook_by_stock(client_id: str, min_days: int | None = None,
                            max_days: int | None = None):
    """Playbook collapsed one row per stock (weighted-avg buy/sell price, total P&L).
    Detail lots for a symbol are fetched via GET /playbook?symbol=... for the
    click-through modal, so this endpoint carries no pagination of its own.
    Optional min_days/max_days slice by holding period (intraday=0..0, week=1..7)."""
    trades = await _trades_or_404(client_id)
    return {"data": analytics.playbook_by_stock(trades, min_days, max_days)}


@router.get("/{client_id}/pnl-calendar")
async def pnl_calendar(client_id: str):
    """P&L calendar: realised daily P&L from closed trades, grouped by sell_date.
    Returns all trading days ever (no date params — frontend paginates by month client-side).
    Cached 300s to match the metrics endpoint."""
    trades = await _trades_or_404(client_id)
    journal = await get_store().get_trade_journal(client_id)
    tags = await get_store().list_tags(client_id)

    # Get closed round-trips from analytics.playbook (the same rows the UI Playbook table shows).
    rows = analytics.playbook(trades, journal, tags)

    # Group by sell_date: aggregate realized P&L, count wins/losses, collect symbols.
    days: dict[str, dict] = {}
    for row in rows:
        sell_date = row.get("sell_date")
        if not sell_date:
            continue

        if sell_date not in days:
            days[sell_date] = {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0, "symbols": set()}

        pnl = row.get("pnl", 0)
        days[sell_date]["pnl"] += pnl
        days[sell_date]["trades"] += 1
        days[sell_date]["wins"] += 1 if pnl > 0 else 0
        days[sell_date]["losses"] += 1 if pnl < 0 else 0
        days[sell_date]["symbols"].add(row["symbol"])

    # Convert sets to sorted lists, round P&L.
    for d in days.values():
        d["pnl"] = round(d["pnl"], 2)
        d["symbols"] = sorted(list(d["symbols"]))

    # Compute month summary: total realised, win/loss day counts, best/worst day.
    total_realized = sum(d["pnl"] for d in days.values())
    win_days = sum(1 for d in days.values() if d["pnl"] > 0)
    loss_days = sum(1 for d in days.values() if d["pnl"] < 0)
    best_day = max(({"date": k, "pnl": v["pnl"]} for k, v in days.items()), key=lambda x: x["pnl"], default=None)
    worst_day = min(({"date": k, "pnl": v["pnl"]} for k, v in days.items()), key=lambda x: x["pnl"], default=None)

    # Date range (earliest/latest sell_date).
    all_dates = sorted(days.keys())
    date_range = {"first": all_dates[0], "last": all_dates[-1]} if all_dates else {}

    return {
        "data": {
            "days": days,
            "summary": {
                "realized": round(total_realized, 2),
                "win_days": win_days,
                "loss_days": loss_days,
                "best_day": best_day,
                "worst_day": worst_day,
            },
            "range": date_range,
        }
    }


@router.get("/{client_id}/holding-summary")
async def holding_summary(client_id: str):
    """Per-stock 'held N days, made/lost X%' rows — fast, no LLM call. The narrative
    is a separate endpoint (below) so the table renders immediately instead of
    waiting 1-3s on Cloudflare; the frontend lazy-loads the narrative after.
    Includes has_thesis per row so closed/no-longer-held positions (this table is the
    only place they're reachable — the Holdings tab only lists what's still open) show
    whether an investment thesis was ever recorded for them."""
    trades = await _trades_or_404(client_id)
    rows = analytics.holding_summary(trades)
    store = get_store()
    theses = await store.list_stock_theses(client_id)
    symbols_with_thesis = {t["symbol"] for t in theses if t.get("thesis") or t.get("target_type")}
    for row in rows:
        row["has_thesis"] = row["symbol"] in symbols_with_thesis
    return {"data": {"rows": rows}}


@router.get("/{client_id}/holding-summary/narrative")
async def holding_summary_narrative(client_id: str):
    """LLM-narrated paragraph over the same rows as /holding-summary (never a
    source of numbers — narration only). Split out because it's the slow part
    (a live LLM call, up to a couple minutes on local Ollama); null if nothing
    is configured or every provider fails, so the frontend just shows the table
    alone. Run off the event loop via run_in_threadpool — narrate() does
    blocking httpx calls, and awaiting it inline would freeze every other
    request on this server for the entire call (single uvicorn worker)."""
    trades = await _trades_or_404(client_id)
    rows = analytics.holding_summary(trades)
    narrative = thinking = None
    if rows:
        narrative, thinking = await run_in_threadpool(narrate, rows)
        if not narrative:
            narrative = fallback_narrate(rows)
    return {"data": {"narrative": narrative, "thinking": thinking}}


@router.get("/{client_id}/dividends")
async def list_dividends(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.list_dividends(client_id)}


@router.post("/{client_id}/dividends")
async def create_dividend(client_id: str, body: DividendCreate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    doc = {**body.model_dump(), "client_id": client_id, "symbol": body.symbol.upper()}
    return {"data": await store.create_dividend(doc)}


@router.patch("/{client_id}/dividends/{div_id}")
async def update_dividend(client_id: str, div_id: str, body: DividendUpdate):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if "symbol" in patch:
        patch["symbol"] = patch["symbol"].upper()
    updated = await store.update_dividend(client_id, div_id, patch)
    if not updated:
        raise HTTPException(404, "dividend not found")
    return {"data": updated}


@router.delete("/{client_id}/dividends/{div_id}")
async def delete_dividend(client_id: str, div_id: str):
    store = get_store()
    ok = await store.delete_dividend(client_id, div_id)
    if not ok:
        raise HTTPException(404, "dividend not found")
    return {"data": {"deleted": True}}


@router.get("/{client_id}/dividends/suggestions")
async def dividend_suggestions(client_id: str, symbol: str | None = None):
    """Propose historical dividends from Yahoo for symbols the client has ever held,
    with the estimated quantity held on each ex-date, for the user to review and accept.
    Never auto-inserted — see store persistence note on the dividends collection."""
    store = get_store()
    trades = await _trades_or_404(client_id)
    existing = await store.list_dividends(client_id)
    already = {(d["symbol"], d["ex_date"]) for d in existing}

    symbols = sorted({t["symbol"] for t in trades})
    if symbol:
        symbol = symbol.upper()
        if symbol not in symbols:
            raise HTTPException(404, "no trades for this symbol")
        symbols = [symbol]

    exchange_by_symbol = {t["symbol"]: t.get("exchange") or "NSE" for t in trades}
    suggestions: list[dict] = []
    for sym in symbols:
        sym_trades = sorted([t for t in trades if t["symbol"] == sym], key=lambda t: t["trade_date"])
        first_date = sym_trades[0]["trade_date"]
        divs = get_dividend_history(sym, exchange_by_symbol.get(sym, "NSE"), from_date=first_date)
        for d in divs:
            if (sym, d["ex_date"]) in already:
                continue
            held_trades = [t for t in sym_trades if t["trade_date"] <= d["ex_date"]]
            if not held_trades:
                continue
            positions, _ = compute_positions(held_trades)
            pos = next((p for p in positions if p.symbol == sym), None)
            qty = pos.quantity if pos else 0
            if qty <= 0:
                continue
            suggestions.append(
                {
                    "symbol": sym,
                    "ex_date": d["ex_date"],
                    "amount_per_share": d["amount_per_share"],
                    "estimated_quantity": qty,
                    "estimated_total": round(d["amount_per_share"] * qty, 2),
                }
            )
    suggestions.sort(key=lambda s: s["ex_date"], reverse=True)
    return {"data": suggestions}


@router.get("/{client_id}/manual-trades")
async def list_manual_trades(client_id: str):
    """Opening/adjustment trades added by hand (source='manual') — for shares not in
    the uploaded tradebook (IPO allotments, bonus/split, pre-window holdings)."""
    trades = await _raw_trades_or_404(client_id)
    manual = [t for t in trades if t.get("source") == "manual"]
    manual.sort(key=lambda t: (t["trade_date"], t.get("symbol", "")))
    return {"data": manual}


@router.post("/{client_id}/manual-trades")
async def add_manual_trade(client_id: str, body: ManualTradeCreate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    ttype = body.trade_type.lower()
    if ttype not in ("buy", "sell"):
        raise HTTPException(422, "trade_type must be 'buy' or 'sell'")
    if body.quantity <= 0 or body.price < 0:
        raise HTTPException(422, "quantity must be > 0 and price >= 0")
    symbol = body.symbol.upper()
    # Deterministic fingerprint so the same opening trade can't be double-added; the
    # uuid keeps intentional duplicates (two real allotment lots) distinct.
    raw = f"manual|{client_id}|{symbol}|{ttype}|{body.quantity}|{body.price}|{body.trade_date}|{uuid.uuid4().hex[:8]}"
    trade = {
        "client_id": client_id,
        "symbol": symbol,
        "trade_type": ttype,
        "quantity": float(body.quantity),
        "price": float(body.price),
        "trade_date": body.trade_date,
        "exchange": "NSE",
        "segment": "", "series": "", "isin": "", "auction": False,
        "charges": 0.0,
        "order_execution_time": f"{body.trade_date}T00:00:00",
        "trade_id": "", "order_id": "",
        "trade_value": round(float(body.quantity) * float(body.price), 4),
        "source": "manual",
        "note": body.note or "",
        "fingerprint": hashlib.sha1(raw.encode()).hexdigest(),
    }
    inserted, _ = await store.insert_trades([trade])
    return {"data": {"inserted": inserted, "trade": trade}}


@router.delete("/{client_id}/manual-trades/{fingerprint}")
async def delete_manual_trade(client_id: str, fingerprint: str):
    store = get_store()
    ok = await store.delete_trade(client_id, fingerprint)
    if not ok:
        raise HTTPException(404, "manual trade not found")
    return {"data": {"deleted": True}}


@router.get("/{client_id}/stocks/{symbol}")
async def stock(client_id: str, symbol: str):
    trades = await _trades_or_404(client_id)
    result = analytics.stock_analysis(trades, symbol, await _actions_for(trades))
    if result is None:
        raise HTTPException(404, "no trades for this symbol")
    return {"data": result}

@router.get("/{client_id}/stocks/{symbol}/thesis")
async def get_stock_thesis(client_id: str, symbol: str):
    await _client_or_404(client_id)
    store = get_store()
    thesis = await store.get_stock_thesis(client_id, symbol)
    return {"data": thesis or {}}

@router.post("/{client_id}/stocks/{symbol}/thesis")
async def save_stock_thesis(client_id: str, symbol: str, body: dict):
    await _client_or_404(client_id)
    store = get_store()
    result = await store.save_stock_thesis(client_id, symbol, body)
    return {"data": result}


@router.get("/{client_id}/thesis-alerts")
async def thesis_alerts(client_id: str):
    """Home-page alerts: currently-held stocks whose thesis target (price or return) has
    been reached ('hit') or is within 10% of being reached ('near'). Drives the
    'Targets to check' card on the client overview."""
    await _client_or_404(client_id)
    store = get_store()
    theses = await store.list_stock_theses(client_id)
    targeted = [t for t in theses if t.get("target_type") and str(t.get("target_value") or "").strip()]
    if not targeted:
        return {"data": []}

    trades = await store.list_trades(client_id)
    holdings_data = analytics.build_holdings(trades, actions=await _actions_for(trades))
    holdings = {h["symbol"]: h for h in holdings_data.get("holdings", [])}

    alerts = []
    for t in targeted:
        sym = t["symbol"]
        h = holdings.get(sym)
        if not h:
            continue  # target only meaningful for a position still held
        try:
            target_val = float(str(t["target_value"]).replace("%", "").replace("₹", "").replace(",", "").strip())
        except (ValueError, TypeError):
            continue
        if target_val == 0:
            continue

        ttype = t["target_type"]
        if "Price" in ttype:
            current = h.get("ltp") or 0
            metric = "price"
        else:  # Return Target (%)
            current = h.get("unrealized_pct")
            metric = "return"
        if current is None:
            continue

        progress = current / target_val * 100
        hit = current >= target_val
        near = (not hit) and progress >= 90
        if hit or near:
            alerts.append({
                "symbol": sym,
                "target_type": ttype,
                "target_value": target_val,
                "current": round(current, 2),
                "metric": metric,
                "status": "hit" if hit else "near",
                "progress_pct": round(progress, 1),
            })

    # hit first, then nearest to target
    alerts.sort(key=lambda a: (a["status"] != "hit", -a["progress_pct"]))
    return {"data": alerts}


# ── Kite broker integration (trades + account data) ────────────────────────────────────
@router.post("/{client_id}/broker/kite/authenticate")
async def kite_authenticate(client_id: str, credentials: dict):
    """Authenticate with Kite and store encrypted credentials for persistent access.
    Body: {api_key, api_secret, user_id, password} — TOTP secret from .env"""
    try:
        from app.services import kite
        from app.config import settings

        # Add TOTP secret from config
        creds_with_totp = {
            **credentials,
            "totp_secret": settings.kite_totp_secret
        }

        # Test credentials
        result = await run_in_threadpool(
            kite.authenticate,
            creds_with_totp
        )
        if not result:
            raise HTTPException(status_code=401, detail="Kite authentication failed")

        access_token, user_data = result

        # Store encrypted credentials
        store = get_store()
        creds_to_store = {
            "api_key": credentials.get("api_key", ""),
            "access_token": access_token,
            "user_id": user_data.get("user_id", ""),
        }
        await store.save_kite_credentials(client_id, creds_to_store)

        return {
            "data": {
                "authenticated": True,
                "user_id": user_data.get("user_id"),
                "user_name": user_data.get("user_name"),
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Kite auth error: {str(e)}")


@router.post("/{client_id}/broker/kite/sync")
async def kite_sync_trades(client_id: str):
    """Fetch trades and account data from Kite, import trades into portfolio.
    Uses 24-hour cache to avoid exhausting rate limits."""
    try:
        from app.services import kite
        from app.config import settings
        from datetime import datetime, timedelta

        store = get_store()
        creds = await store.get_kite_credentials(client_id)
        if not creds:
            raise HTTPException(
                status_code=400,
                detail="Kite credentials not found. Please authenticate first."
            )

        # Check cache first
        cached = await store.get_kite_sync_cache(client_id)
        cache_valid = False
        if cached and cached.get("synced_at"):
            age = datetime.utcnow() - cached["synced_at"]
            cache_valid = age < timedelta(seconds=settings.kite_sync_cache_ttl_seconds)

        if cache_valid:
            # Use cached data
            trades_list = cached.get("trades", [])
            cash_info = cached.get("cash", {})
            from_cache = True
        else:
            # Fetch fresh from Kite (only ~4 API calls)
            summary = await run_in_threadpool(
                kite.account_summary,
                creds.get("access_token"),
                creds.get("api_key")
            )
            if not summary:
                raise HTTPException(status_code=401, detail="Kite sync failed")

            trades_list = summary.get("trades", [])
            cash_info = summary.get("cash", {})

            # Cache for next 24 hours
            await store.save_kite_sync_cache(client_id, summary)
            from_cache = False

        # Import trades (deduped by fingerprint)
        imported = 0
        duplicates = 0
        errors = 0

        existing_trades = await store.list_trades(client_id)
        existing_fps = {t.get("fingerprint") for t in existing_trades}

        for kite_trade in trades_list:
            try:
                trade = {
                    "trade_date": kite_trade["trade_date"],
                    "symbol": kite_trade["symbol"],
                    "action": kite_trade["action"],
                    "quantity": kite_trade["quantity"],
                    "price": kite_trade["price"],
                    "broker_id": kite_trade.get("broker_id", "kite"),
                }

                # Create fingerprint
                fp = hashlib.sha256(
                    f"{trade['trade_date']}{trade['symbol']}{trade['action']}{trade['quantity']}{trade['price']}".encode()
                ).hexdigest()

                if fp in existing_fps:
                    duplicates += 1
                    continue

                trade["fingerprint"] = fp
                await store.insert_trades([trade])
                imported += 1

            except Exception as e:
                errors += 1
                print(f"Error importing Kite trade: {e}")

        return {
            "data": {
                "imported": imported,
                "duplicates": duplicates,
                "errors": errors,
                "cash": cash_info.get("cash", 0),
                "available": cash_info.get("available_balance", 0),
                "from_cache": from_cache,
                "message": "Data from 24-hour cache" if from_cache else "Fresh data from Kite API",
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{client_id}/broker/kite/status")
async def kite_broker_status(client_id: str):
    """Check Kite authentication status."""
    try:
        store = get_store()
        creds = await store.get_kite_credentials(client_id)
        return {"data": {"authenticated": creds is not None}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Multi-Account Kite Management ────────────────────────────────────────────────────────

@router.get("/{client_id}/broker/kite/accounts")
async def list_kite_accounts(client_id: str):
    """List all Kite accounts for a client with cached user profiles."""
    try:
        store = get_store()
        accounts = await store.list_kite_accounts(client_id)
        return {
            "data": {
                "accounts": [
                    {
                        "id": a["id"],
                        "name": a.get("name", ""),
                        "owner": a.get("owner", ""),
                        "is_active": a.get("is_active", False),
                        "created_at": a.get("created_at"),
                        "synced_at": a.get("synced_at"),
                        "profile_fetched_at": a.get("profile_fetched_at"),
                        "user_name": a.get("profile", {}).get("user_name"),
                        "email": a.get("profile", {}).get("email"),
                        "phone": a.get("profile", {}).get("phone"),
                        "account_type": a.get("profile", {}).get("account_type"),
                    }
                    for a in accounts
                ]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{client_id}/broker/kite/accounts")
async def add_kite_account(client_id: str, account: dict):
    """Add a new Kite account for a client.

    TWO WAYS TO ADD ACCOUNT:

    1. TOKEN-BASED (Recommended - No CAPTCHA):
       Body: {name, owner, api_key, access_token}
       Steps: User logs in manually via browser, copies access_token, provides here

    2. PROGRAMMATIC (Requires CAPTCHA):
       Body: {name, owner, api_key, api_secret, user_id, password, totp_secret}
       Will attempt automated login (may fail with CAPTCHA)

    Returns: Account details with cached user profile
    """
    try:
        from app.services import kite

        api_key = account.get("api_key")
        if not api_key:
            raise HTTPException(status_code=400, detail="api_key is required")

        # Check if using token-based auth
        access_token = account.get("access_token")
        if access_token:
            # TOKEN-BASED AUTH (preferred)
            profile = await run_in_threadpool(
                kite.validate_access_token, access_token, api_key
            )
            if not profile:
                raise HTTPException(
                    status_code=401,
                    detail="Invalid access token. Please log in to Kite and get a new token."
                )
        else:
            # PROGRAMMATIC AUTH (fallback)
            creds = {
                "api_key": api_key,
                "api_secret": account.get("api_secret"),
                "user_id": account.get("user_id"),
                "password": account.get("password"),
                "totp_secret": account.get("totp_secret"),
            }

            auth_result = await run_in_threadpool(kite.authenticate, creds)
            if not auth_result:
                raise HTTPException(
                    status_code=401,
                    detail="Kite authentication failed (likely CAPTCHA required). Use token-based auth instead."
                )

            access_token, _ = auth_result

            # Fetch user profile from Kite
            profile = await run_in_threadpool(kite.user_profile, access_token, api_key)
            if not profile:
                raise HTTPException(status_code=400, detail="Could not fetch user profile from Kite")

        store = get_store()
        new_account = await store.add_kite_account(client_id, account)

        # Save the user profile
        await store.save_kite_account_profile(client_id, new_account["id"], profile)

        return {
            "data": {
                "account": {
                    "id": new_account["id"],
                    "name": new_account.get("name"),
                    "owner": new_account.get("owner"),
                    "is_active": new_account.get("is_active"),
                    "user_name": profile.get("user_name"),
                    "email": profile.get("email"),
                    "phone": profile.get("phone"),
                    "account_type": profile.get("account_type"),
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error adding Kite account: {str(e)}")


@router.delete("/{client_id}/broker/kite/accounts/{account_id}")
async def delete_kite_account(client_id: str, account_id: str):
    """Delete a Kite account."""
    try:
        store = get_store()
        deleted = await store.delete_kite_account(client_id, account_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"data": {"deleted": True}}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{client_id}/broker/kite/accounts/{account_id}/select")
async def select_kite_account(client_id: str, account_id: str):
    """Set a Kite account as the active account."""
    try:
        store = get_store()
        account = await store.set_active_kite_account(client_id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return {
            "data": {
                "account": {
                    "id": account["id"],
                    "name": account.get("name"),
                    "is_active": account.get("is_active"),
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{client_id}/broker/kite/accounts/{account_id}/sync")
async def sync_kite_account(client_id: str, account_id: str):
    """Manually sync trades, holdings, cash for a specific Kite account.

    Only fetches when explicitly called (no daily auto-sync).
    Caches for 24 hours to avoid rate limit exhaustion.
    """
    try:
        from app.services import kite
        from datetime import datetime, timedelta

        store = get_store()

        # Get account with decrypted credentials
        account = await store.get_kite_account(client_id, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")

        creds = account.get("credentials", {})

        # Check cache (24-hour TTL)
        cached = await store.get_kite_sync_cache(client_id)
        if cached:
            synced_at = cached.get("synced_at")
            if synced_at:
                age = (datetime.utcnow() - synced_at).total_seconds()
                cache_ttl = 86400  # 24 hours
                if age < cache_ttl:
                    return {
                        "data": {
                            "trades": cached.get("trades", []),
                            "holdings": cached.get("holdings", []),
                            "cash": cached.get("cash", {}),
                            "from_cache": True,
                            "message": f"Data from cache ({int(age/3600)}h old)",
                            "last_synced": synced_at.isoformat(),
                        }
                    }

        # Authenticate and fetch fresh data
        auth_result = await run_in_threadpool(kite.authenticate, creds)
        if not auth_result:
            raise HTTPException(status_code=401, detail="Kite authentication failed")

        access_token, _ = auth_result

        # Fetch account summary
        summary = await run_in_threadpool(kite.account_summary, access_token, creds.get("api_key"))
        if not summary:
            raise HTTPException(status_code=500, detail="Failed to fetch account data")

        # Cache the data
        await store.save_kite_sync_cache(client_id, summary)

        # Get trades from cache (import to portfolio happens in next phase)
        trades_list = summary.get("trades", [])

        return {
            "data": {
                "trades": trades_list,
                "holdings": summary.get("holdings", []),
                "cash": summary.get("cash", {}),
                "from_cache": False,
                "message": f"Synced {len(trades_list)} trades",
                "imported": len(trades_list),
                "last_synced": datetime.utcnow().isoformat(),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Account sync error: {e}")
        raise HTTPException(status_code=500, detail=f"Sync error: {str(e)}")


# ── Angel One market data (persistent credentials) ────────────────────────────────────
@router.post("/{client_id}/broker/angel/authenticate")
async def angel_authenticate(client_id: str, credentials: dict):
    """Store Angel One credentials for persistent market data access (quotes, historical prices).
    Trades still come from Kite uploads. Credentials are encrypted.
    Body: {client_id, api_key, pin, totp_secret}"""
    try:
        import pyotp
        from SmartApi import SmartConnect

        # Test credentials before saving
        smart = SmartConnect(api_key=credentials.get("api_key"))
        totp = pyotp.TOTP(credentials.get("totp_secret")).now()
        resp = smart.generateSession(
            credentials.get("client_id"),
            credentials.get("pin"),
            totp
        )
        if not resp.get("status"):
            raise HTTPException(status_code=401, detail=f"Angel auth failed: {resp.get('message')}")

        # Store encrypted credentials for future data fetches
        store = get_store()
        await store.save_angel_credentials(client_id, credentials)

        return {"data": {"authenticated": True, "message": "Angel One connected. Now quotes come from Angel (not Yahoo Finance)."}}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Angel auth error: {str(e)}")


@router.get("/{client_id}/broker/angel/status")
async def angel_broker_status(client_id: str):
    """Check if Angel One credentials are available for this client."""
    try:
        store = get_store()
        creds = await store.get_angel_credentials(client_id)
        return {"data": {"authenticated": creds is not None, "purpose": "market data (quotes, prices)"}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
