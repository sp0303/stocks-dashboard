"""Portfolio analytics — assembles dashboard payloads from trades + live quotes + sectors.

Everything here is derived. The FIFO engine owns positions/realized P&L; this module layers
market valuation, allocation, concentration, performance series and per-stock analysis.
"""
from __future__ import annotations

from collections import defaultdict

from app.services.engine import compute_positions
from app.services.market_data import get_quotes
from app.services.securities import classify


def _exchange_map(trades: list[dict]) -> dict[str, str]:
    """Prefer NSE when a symbol trades on both (yfinance .NS coverage is better)."""
    ex: dict[str, str] = {}
    for t in trades:
        s = t["symbol"]
        if ex.get(s) != "NSE":
            ex[s] = t.get("exchange") or "NSE"
    return ex


def build_holdings(trades: list[dict], with_prices: bool = True) -> dict:
    positions, total_realized = compute_positions(trades)
    open_pos = [p for p in positions if p.quantity > 0]
    symbols = [p.symbol for p in open_pos]
    quotes = get_quotes(symbols, _exchange_map(trades)) if (with_prices and symbols) else {}

    holdings = []
    total_market = total_invested = total_unrealized = 0.0
    for p in open_pos:
        meta = classify(p.symbol)
        q = quotes.get(p.symbol, {})
        ltp = q.get("price")
        invested = p.invested_value
        market_value = (ltp * p.quantity) if ltp is not None else None
        unrealized = (market_value - invested) if market_value is not None else None
        total_invested += invested
        if market_value is not None:
            total_market += market_value
            total_unrealized += unrealized
        holdings.append(
            {
                "symbol": p.symbol,
                "quantity": p.quantity,
                "avg_cost": round(p.avg_cost, 2),
                "ltp": ltp,
                "invested_value": round(invested, 2),
                "market_value": round(market_value, 2) if market_value is not None else None,
                "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
                "unrealized_pct": round(unrealized / invested * 100, 2)
                if unrealized is not None and invested
                else None,
                "sector": meta["sector"],
                "asset_class": meta["asset_class"],
                "cap": meta["cap"],
                "stale": q.get("stale", True),
            }
        )
    # portfolio weight
    for h in holdings:
        h["portfolio_pct"] = (
            round(h["market_value"] / total_market * 100, 2)
            if h["market_value"] and total_market
            else None
        )
    holdings.sort(key=lambda h: h["market_value"] or 0, reverse=True)

    return {
        "holdings": holdings,
        "totals": {
            "invested_value": round(total_invested, 2),
            "market_value": round(total_market, 2),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(total_realized + total_unrealized, 2),
            "return_pct": round((total_realized + total_unrealized) / total_invested * 100, 2)
            if total_invested
            else 0.0,
            "open_positions": len(holdings),
        },
        "_positions": positions,
    }


def portfolio_summary(trades: list[dict]) -> dict:
    data = build_holdings(trades)
    t = data["totals"]
    buys = sum(1 for x in trades if x["trade_type"] == "buy")
    sells = len(trades) - buys
    return {
        **t,
        "total_trades": len(trades),
        "buy_trades": buys,
        "sell_trades": sells,
    }


def allocation(trades: list[dict], by: str = "sector", basis: str = "current") -> list[dict]:
    """Weight buckets by live market value ("current" — today's mark-to-market split)
    or by original invested/cost value ("invested" — how capital was actually deployed,
    unaffected by subsequent price moves). Same buckets, different weighting basis."""
    data = build_holdings(trades)
    value_field = "market_value" if basis == "current" else "invested_value"
    total = data["totals"][value_field] or 0
    buckets: dict[str, float] = defaultdict(float)
    for h in data["holdings"]:
        v = h[value_field]
        if v is None:
            continue
        key = {
            "sector": h["sector"], "asset": h["asset_class"], "stock": h["symbol"], "cap": h["cap"],
        }.get(by, h["sector"])
        buckets[key] += v
    out = [
        {"key": k, "value": round(v, 2), "pct": round(v / total * 100, 2) if total else 0.0}
        for k, v in buckets.items()
    ]
    out.sort(key=lambda x: x["value"], reverse=True)
    return out


def concentration(trades: list[dict]) -> dict:
    data = build_holdings(trades)
    total = data["totals"]["market_value"] or 0
    hs = sorted(
        (h for h in data["holdings"] if h["market_value"]),
        key=lambda h: h["market_value"],
        reverse=True,
    )
    top5 = sum(h["market_value"] for h in hs[:5])
    sectors = allocation(trades, "sector")
    return {
        "top5_pct": round(top5 / total * 100, 2) if total else 0.0,
        "largest_stock": {"symbol": hs[0]["symbol"], "pct": hs[0]["portfolio_pct"]}
        if hs
        else None,
        "largest_sector": {"key": sectors[0]["key"], "pct": sectors[0]["pct"]}
        if sectors
        else None,
        "holdings_count": len(hs),
    }


def performance_series(trades: list[dict]) -> list[dict]:
    """Cumulative invested & realized over time (daily). A cost-basis performance view
    that needs no historical price backfill — realized P&L and net deployed capital by date.
    """
    ts = sorted(trades, key=lambda t: t["trade_date"])
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        by_day[t["trade_date"]].append(t)

    cumulative: list[dict] = []
    running: list[dict] = []
    for day in sorted(by_day):
        running.extend(by_day[day])
        positions, realized = compute_positions(running)
        invested = sum(p.invested_value for p in positions if p.quantity > 0)
        cumulative.append(
            {
                "date": day,
                "invested_value": round(invested, 2),
                "realized_pnl": round(realized, 2),
            }
        )
    return cumulative


def portfolio_value_series(trades: list[dict], from_date: str | None = None) -> list[dict]:
    """True day-by-day mark-to-market portfolio value, using each held symbol's real
    historical closing price (not cost basis). One history fetch per symbol ever
    traded, not per day, so this stays cheap even over a multi-year window.

    Forward-fills a symbol's price on days it didn't trade (holidays, illiquidity).
    """
    from concurrent.futures import ThreadPoolExecutor

    from app.services.market_data import get_history

    ts = sorted(trades, key=lambda t: t["trade_date"])
    if not ts:
        return []
    start = from_date or ts[0]["trade_date"]
    symbols = sorted({t["symbol"] for t in ts})
    exchanges = _exchange_map(ts)

    def fetch(sym: str):
        h = get_history(sym, from_date=ts[0]["trade_date"], interval="1d", exchange=exchanges.get(sym, "NSE"))
        return sym, {p["date"]: p["close"] for p in h.get("points", [])}

    price_by_symbol: dict[str, dict[str, float]] = {}
    with ThreadPoolExecutor(max_workers=10) as ex:
        for sym, series in ex.map(fetch, symbols):
            price_by_symbol[sym] = series

    all_dates = sorted({d for series in price_by_symbol.values() for d in series if d >= start})
    if not all_dates:
        return []

    trades_by_date: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        trades_by_date[t["trade_date"]].append(t)
    trade_dates_sorted = sorted(trades_by_date.keys())

    qty: dict[str, float] = defaultdict(float)
    last_price: dict[str, float] = {}
    out = []
    ti = 0
    for day in all_dates:
        while ti < len(trade_dates_sorted) and trade_dates_sorted[ti] <= day:
            for t in trades_by_date[trade_dates_sorted[ti]]:
                delta = t["quantity"] if t["trade_type"] == "buy" else -t["quantity"]
                qty[t["symbol"]] += delta
            ti += 1
        mv = 0.0
        for sym, q in qty.items():
            if q <= 1e-9:
                continue
            series = price_by_symbol.get(sym, {})
            if day in series:
                last_price[sym] = series[day]
            px = last_price.get(sym)
            if px is not None:
                mv += px * q
        out.append({"date": day, "market_value": round(mv, 2)})
    return out


def benchmark_comparison(trades: list[dict], from_date: str | None = None) -> dict:
    """Portfolio market value vs Nifty 50 / Sensex, all indexed to 100 at the start
    of the window so the three lines are directly comparable ("mine vs Nifty vs
    Sensex"). Approximate — it does not correct for mid-period cash flows the way
    a true time-weighted return would, but it's the standard retail-app comparison.
    """
    from app.services.market_data import BENCHMARKS, get_history

    pv = portfolio_value_series(trades, from_date)
    if not pv:
        return {"series": [], "start_date": from_date}
    start = pv[0]["date"]
    base_mv = pv[0]["market_value"]

    portfolio_by_date = {p["date"]: p["market_value"] for p in pv}

    benchmark_series: dict[str, dict[str, float]] = {}
    benchmark_base: dict[str, float | None] = {}
    for key, meta in BENCHMARKS.items():
        h = get_history(meta["ticker"], from_date=start, interval="1d", exchange="INDEX")
        pts = h.get("points", [])
        benchmark_series[key] = {p["date"]: p["close"] for p in pts}
        benchmark_base[key] = pts[0]["close"] if pts else None

    all_dates = sorted(set(portfolio_by_date) | {d for s in benchmark_series.values() for d in s})
    all_dates = [d for d in all_dates if d >= start]

    last_bm: dict[str, float] = {}
    last_pv = base_mv
    out = []
    for day in all_dates:
        if day in portfolio_by_date:
            last_pv = portfolio_by_date[day]
        row = {"date": day, "portfolio_pct": round((last_pv - base_mv) / base_mv * 100, 2) if base_mv else 0.0}
        for key, series in benchmark_series.items():
            if day in series:
                last_bm[key] = series[day]
            base_bm = benchmark_base[key]
            row[f"{key}_pct"] = (
                round((last_bm[key] - base_bm) / base_bm * 100, 2)
                if base_bm and key in last_bm else None
            )
        out.append(row)
    return {"series": out, "start_date": start, "benchmarks": {k: v["label"] for k, v in BENCHMARKS.items()}}


def manager_metrics(clients: list[dict]) -> dict:
    """Aggregate across all of a manager's clients.

    `clients` = [{"id","name","trades":[...]}]. One quote fetch for the whole book.
    """
    from collections import defaultdict

    # per-symbol aggregates across the whole book
    invested_by_sym: dict[str, float] = defaultdict(float)
    qty_by_sym: dict[str, float] = defaultdict(float)
    realized_by_sym: dict[str, float] = defaultdict(float)
    trade_count_by_sym: dict[str, int] = defaultdict(int)
    exchanges: dict[str, str] = {}

    total_realized = 0.0
    per_client_open: list[tuple[str, str, list]] = []  # (client_id, name, open positions)
    all_symbols: set[str] = set()

    for c in clients:
        trades = c.get("trades", [])
        for t in trades:
            trade_count_by_sym[t["symbol"]] += 1
            if exchanges.get(t["symbol"]) != "NSE":
                exchanges[t["symbol"]] = t.get("exchange") or "NSE"
        positions, realized = compute_positions(trades)
        total_realized += realized
        opens = [p for p in positions if p.quantity > 0]
        per_client_open.append((c["id"], c.get("name", ""), opens))
        for p in opens:
            invested_by_sym[p.symbol] += p.invested_value
            qty_by_sym[p.symbol] += p.quantity
            all_symbols.add(p.symbol)
        for p in positions:
            realized_by_sym[p.symbol] += p.realized_pnl

    quotes = get_quotes(sorted(all_symbols), exchanges) if all_symbols else {}

    # book-wide valuation
    total_invested = sum(invested_by_sym.values())
    market_by_sym: dict[str, float] = {}
    total_market = total_unrealized = 0.0
    for sym, qty in qty_by_sym.items():
        ltp = quotes.get(sym, {}).get("price")
        if ltp is None:
            continue
        mv = ltp * qty
        market_by_sym[sym] = mv
        total_market += mv
        total_unrealized += mv - invested_by_sym[sym]

    # per-client rollup (market value + total pnl)
    by_client = []
    for cid, name, opens in per_client_open:
        cinv = sum(p.invested_value for p in opens)
        cmv = sum((quotes.get(p.symbol, {}).get("price") or 0) * p.quantity for p in opens)
        crealized = sum(p.realized_pnl for p in opens)  # realized on still-open symbols only
        by_client.append({
            "client_id": cid, "name": name,
            "invested": round(cinv, 2), "market_value": round(cmv, 2),
            "unrealized_pnl": round(cmv - cinv, 2) if cmv else 0.0,
        })
    by_client.sort(key=lambda x: x["market_value"], reverse=True)

    def top(d):
        return max(d.items(), key=lambda kv: kv[1]) if d else None

    most_invested = top(invested_by_sym)
    favourite = top(trade_count_by_sym)
    top_hold = top(market_by_sym)
    # best/worst by unrealized %
    perf = {
        s: (market_by_sym[s] - invested_by_sym[s]) / invested_by_sym[s] * 100
        for s in market_by_sym if invested_by_sym[s]
    }
    best = max(perf.items(), key=lambda kv: kv[1]) if perf else None
    worst = min(perf.items(), key=lambda kv: kv[1]) if perf else None

    return {
        "totals": {
            "clients": len(clients),
            "invested_value": round(total_invested, 2),
            "market_value": round(total_market, 2),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(total_realized + total_unrealized, 2),
            "return_pct": round((total_realized + total_unrealized) / total_invested * 100, 2) if total_invested else 0.0,
            "unique_stocks": len(all_symbols),
        },
        "most_invested_stock": {"symbol": most_invested[0], "invested_value": round(most_invested[1], 2)} if most_invested else None,
        "favourite_stock": {"symbol": favourite[0], "trade_count": favourite[1]} if favourite else None,
        "top_holding": {"symbol": top_hold[0], "market_value": round(top_hold[1], 2)} if top_hold else None,
        "best_performer": {"symbol": best[0], "pct": round(best[1], 2)} if best else None,
        "worst_performer": {"symbol": worst[0], "pct": round(worst[1], 2)} if worst else None,
        "by_client": by_client,
    }


def stock_analysis(trades: list[dict], symbol: str) -> dict | None:
    symbol = symbol.upper()
    sym_trades = [t for t in trades if t["symbol"] == symbol]
    if not sym_trades:
        return None
    positions, _ = compute_positions(trades)
    pos = next((p for p in positions if p.symbol == symbol), None)
    meta = classify(symbol)
    quotes = get_quotes([symbol], _exchange_map(trades))
    ltp = quotes.get(symbol, {}).get("price")
    market_value = (ltp * pos.quantity) if (ltp and pos and pos.quantity) else None
    unrealized = (market_value - pos.invested_value) if market_value is not None else None
    timeline = [
        {
            "date": t["trade_date"],
            "type": t["trade_type"],
            "quantity": t["quantity"],
            "price": t["price"],
            "value": t["trade_value"],
        }
        for t in sorted(sym_trades, key=lambda t: (t["trade_date"], t["order_execution_time"]))
    ]
    return {
        "symbol": symbol,
        "sector": meta["sector"],
        "asset_class": meta["asset_class"],
        "cap": meta["cap"],
        "current_quantity": pos.quantity if pos else 0,
        "avg_cost": round(pos.avg_cost, 2) if pos else 0,
        "ltp": ltp,
        "first_buy_date": pos.first_buy_date if pos else None,
        "last_buy_date": pos.last_buy_date if pos else None,
        "last_sell_date": pos.last_sell_date if pos else None,
        "total_bought_qty": pos.total_bought_qty if pos else 0,
        "total_sold_qty": pos.total_sold_qty if pos else 0,
        "total_bought_value": round(pos.total_bought_value, 2) if pos else 0,
        "total_sold_value": round(pos.total_sold_value, 2) if pos else 0,
        "market_value": round(market_value, 2) if market_value is not None else None,
        "realized_pnl": round(pos.realized_pnl, 2) if pos else 0,
        "unrealized_pnl": round(unrealized, 2) if unrealized is not None else None,
        "total_pnl": round((pos.realized_pnl if pos else 0) + (unrealized or 0), 2),
        "timeline": timeline,
    }
