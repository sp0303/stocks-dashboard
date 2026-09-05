"""Portfolio analytics routes (read-only, derived)."""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

import hashlib
import uuid

from app.models.schemas import (
    DividendCreate, DividendUpdate, ManualTradeCreate, TagCreate, TagUpdate, TradeNoteUpdate, TradeTagsUpdate,
)
from app.services import analytics
from app.services.engine import compute_positions
from app.services.llm import fallback_narrate, narrate
from app.services.market_data import get_dividend_history
from app.store import get_store

router = APIRouter(prefix="/api/clients", tags=["portfolio"])

BENCHMARK_SYMBOL = "^NSEI"


async def _benchmark_price_map(trades: list[dict]) -> dict[str, float]:
    """Cached-first Nifty close series covering the client's trading history. Only the
    dates missing from the store's `benchmark_prices` cache are fetched from Yahoo."""
    if not trades:
        return {}
    store = get_store()
    cached = await store.get_benchmark_prices(BENCHMARK_SYMBOL)
    first_trade_date = min(t["trade_date"] for t in trades)
    today = date.today().strftime("%Y-%m-%d")

    have_recent = cached and max(cached.keys()) >= (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")
    if cached and have_recent and min(cached.keys()) <= first_trade_date:
        return cached

    # Index tickers (^NSEI) don't take the NSE/.NS suffix rewrite that get_history applies
    # to equities, so fetch the raw ticker directly.
    fetched = _fetch_index_history(first_trade_date, today)
    new_prices = {p["date"]: p["close"] for p in fetched}
    if new_prices:
        await store.save_benchmark_prices(BENCHMARK_SYMBOL, new_prices)
    merged = {**cached, **new_prices}
    return merged


def _fetch_index_history(from_date: str, to_date: str) -> list[dict]:
    """`^NSEI` needs the raw Yahoo ticker (no .NS/.BO suffix), so this bypasses
    market_data.get_history's equity-ticker rewriting and hits the chart endpoint directly."""
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
        url = f"{host}/v8/finance/chart/{BENCHMARK_SYMBOL}?period1={p1}&period2={p2}&interval=1d"
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


async def _trades_or_404(client_id: str) -> list[dict]:
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return await store.list_trades(client_id)


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


@router.get("/{client_id}/performance")
async def performance(client_id: str):
    trades = await _trades_or_404(client_id)
    series = analytics.performance_series(trades)
    prices = await _benchmark_price_map(trades)
    if prices:
        bench = {row["date"]: row["benchmark_value"] for row in analytics.benchmark_series(trades, prices)}
        for row in series:
            row["benchmark_value"] = bench.get(row["date"])
    return {"data": series}


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
    store = get_store()
    ts = await _trades_or_404(client_id)
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
async def playbook_by_stock(client_id: str):
    """Playbook collapsed one row per stock (weighted-avg buy/sell price, total P&L).
    Detail lots for a symbol are fetched via GET /playbook?symbol=... for the
    click-through modal, so this endpoint carries no pagination of its own."""
    trades = await _trades_or_404(client_id)
    return {"data": analytics.playbook_by_stock(trades)}


@router.get("/{client_id}/holding-summary")
async def holding_summary(client_id: str):
    """Per-stock 'held N days, made/lost X%' rows — fast, no LLM call. The narrative
    is a separate endpoint (below) so the table renders immediately instead of
    waiting 1-3s on Cloudflare; the frontend lazy-loads the narrative after."""
    trades = await _trades_or_404(client_id)
    rows = analytics.holding_summary(trades)
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
    trades = await _trades_or_404(client_id)
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
    thesis = await store.get_stock_thesis(client_id, symbol)
    return {"data": thesis or {}}

@router.post("/{client_id}/stocks/{symbol}/thesis")
async def save_stock_thesis(client_id: str, symbol: str, body: dict):
    await _client_or_404(client_id)
    result = await store.save_stock_thesis(client_id, symbol, body)
    return {"data": result}
