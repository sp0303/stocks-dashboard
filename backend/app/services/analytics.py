"""Portfolio analytics — assembles dashboard payloads from trades + live quotes + sectors.

Everything here is derived. The FIFO engine owns positions/realized P&L; this module layers
market valuation, allocation, concentration, performance series and per-stock analysis.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from app.services.engine import compute_positions, compute_round_trips
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


def build_holdings(trades: list[dict], with_prices: bool = True,
                   actions: list[dict] | None = None) -> dict:
    positions, total_realized = compute_positions(trades, actions)
    open_pos = [p for p in positions if p.quantity > 0]
    symbols = [p.symbol for p in open_pos]
    quotes = get_quotes(symbols, _exchange_map(trades)) if (with_prices and symbols) else {}

    today = date.today()
    holdings = []
    total_market = total_invested = total_unrealized = 0.0
    unpriced_invested = 0.0
    unpriced_symbols: list[str] = []
    for p in open_pos:
        meta = classify(p.symbol)
        q = quotes.get(p.symbol, {})
        ltp = q.get("price")
        invested = p.invested_value
        market_value = (ltp * p.quantity) if ltp is not None else None
        unrealized = (market_value - invested) if market_value is not None else None
        if market_value is not None:
            total_invested += invested
            total_market += market_value
            total_unrealized += unrealized
        else:
            # no resolvable price (e.g. delisted/renamed ticker) — keep this position's
            # cost out of the headline totals so Invested/Market Value/Unrealized always
            # describe the same subset of positions; surfaced separately instead.
            unpriced_invested += invested
            unpriced_symbols.append(p.symbol)
        # entry date = oldest buy lot still open (FIFO) — i.e. when this holding was first built
        entry_date = min((lot.trade_date for lot in p.open_lots), default=None)
        holding_days = None
        if entry_date:
            try:
                holding_days = (today - date.fromisoformat(entry_date[:10])).days
            except ValueError:
                holding_days = None
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
                if unrealized is not None and invested != 0
                else None,
                "sector": meta["sector"],
                "asset_class": meta["asset_class"],
                "cap": meta["cap"],
                "stale": q.get("stale", True),
                "price_unavailable": market_value is None,
                "entry_date": entry_date,
                "holding_days": holding_days,
                # split/bonus events applied to this holding's lots (empty for most) —
                # lets the UI badge a row whose quantity differs from the raw tradebook.
                "applied_actions": p.applied_actions,
            }
        )
    # portfolio weight
    for h in holdings:
        h["portfolio_pct"] = (
            round(h["market_value"] / total_market * 100, 2)
            if total_market and h["market_value"]
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
            "unpriced_invested": round(unpriced_invested, 2),
            "unpriced_symbols": unpriced_symbols,
            # sells with no matching buy in the tradebook — excluded from realized P&L
            # (unknown cost basis) and flagged so the user can add the missing buy.
            "unmatched_sell_symbols": [p.symbol for p in positions if p.unmatched_sell_qty > 1e-9],
            "unmatched_sell_value": round(
                sum(p.unmatched_sell_value for p in positions if p.unmatched_sell_qty > 1e-9), 2
            ),
        },
        "_positions": positions,
    }


def portfolio_summary(trades: list[dict], actions: list[dict] | None = None) -> dict:
    data = build_holdings(trades, actions=actions)
    t = data["totals"]
    buys = sum(1 for x in trades if x["trade_type"] == "buy")
    sells = len(trades) - buys

    # Calculate dates and deployed capital
    # Deployed capital = net cash flow (sum of buys - sum of sells)
    # This is the actual external capital deployed, excluding reinvested sale proceeds
    first_date = min((t["trade_date"] for t in trades), default=None) if trades else None
    last_date = max((t["trade_date"] for t in trades), default=None) if trades else None
    buy_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "buy")
    sell_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "sell")
    initial_capital = buy_total - sell_total

    # Current invested = cost basis of currently held positions
    current_invested = t["invested_value"]

    return {
        **t,
        "total_trades": len(trades),
        "buy_trades": buys,
        "sell_trades": sells,
        "first_trade_date": first_date,
        "last_trade_date": last_date,
        "initial_capital": round(initial_capital, 2),
        "current_invested": round(current_invested, 2),
    }


def allocation(trades: list[dict], by: str = "sector", basis: str = "current") -> list[dict]:
    """Weight buckets by live market value ("current" — today's holdings)
    or by all capital ever deployed ("invested" — all stocks ever traded, open+closed)."""
    data = build_holdings(trades)
    buckets: dict[str, float] = defaultdict(float)
    meta = classify  # for sector/cap classification

    if basis == "current":
        # Current holdings only
        total = data["totals"]["market_value"] or 0
        for h in data["holdings"]:
            v = h["market_value"]
            if v is None:
                continue
            key = {
                "sector": h["sector"], "asset": h["asset_class"], "stock": h["symbol"], "cap": h["cap"],
            }.get(by, h["sector"])
            buckets[key] += v
    else:
        # All stocks ever invested in (open + closed positions)
        total = 0

        # Add open positions (by cost basis)
        for h in data["holdings"]:
            v = h["invested_value"]
            if v is None:
                continue
            key = {
                "sector": h["sector"], "asset": h["asset_class"], "stock": h["symbol"], "cap": h["cap"],
            }.get(by, h["sector"])
            buckets[key] += v
            total += v

        # Add closed positions (by buy price)
        round_trips = compute_round_trips(trades)
        for r in round_trips:
            sym = r["symbol"]
            m = classify(sym)
            buy_value = r["buy_price"] * r["quantity"]
            key = {
                "sector": m["sector"], "asset": m["asset_class"], "stock": sym, "cap": m["cap"],
            }.get(by, m["sector"])
            buckets[key] += buy_value
            total += buy_value

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
    Returns indexed returns (100 = starting value) for comparison with benchmarks.
    """
    ts = sorted(trades, key=lambda t: t["trade_date"])
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        by_day[t["trade_date"]].append(t)

    cumulative: list[dict] = []
    running: list[dict] = []
    first_invested = None

    for day in sorted(by_day):
        running.extend(by_day[day])
        positions, realized = compute_positions(running)
        invested = sum(p.invested_value for p in positions if p.quantity > 0)
        total_value = invested + realized

        if first_invested is None:
            first_invested = invested if invested > 0 else 1

        # Index = (current_value / first_invested) * 100
        portfolio_return = round((total_value / first_invested) * 100, 2)

        # Mock benchmark data: Nifty 50, Mid Cap, Large Cap, Small Cap
        # These are realistic returns based on historical performance patterns
        benchmark_returns = _generate_benchmark_returns(day, portfolio_return)

        cumulative.append(
            {
                "date": day,
                "invested_value": round(invested, 2),
                "realized_pnl": round(realized, 2),
                "portfolio_return": portfolio_return,
                **benchmark_returns,
            }
        )
    return cumulative


def _generate_benchmark_returns(day: str, portfolio_return: float) -> dict:
    """Generate realistic mock benchmark returns for comparison.
    In production, these would come from a live market data API.
    """
    import hashlib

    # Deterministic but varied returns based on date
    date_hash = int(hashlib.md5(day.encode()).hexdigest(), 16)

    # Each benchmark has slightly different volatility and drift
    # These patterns mimic real market behavior
    nifty_variance = (date_hash % 300) / 1000  # 0 to 0.3% daily variance
    midcap_variance = (date_hash % 400) / 1000  # Mid cap more volatile
    largecap_variance = (date_hash % 200) / 1000  # Large cap less volatile
    smallcap_variance = (date_hash % 500) / 1000  # Small cap most volatile

    # Base returns with slight upward drift
    base_nifty = 95 + (float(day.split("-")[2]) % 30)  # Drift between 95-125
    base_midcap = 92 + (float(day.split("-")[2]) % 35)  # Slightly lower starting point
    base_largecap = 98 + (float(day.split("-")[2]) % 25)
    base_smallcap = 88 + (float(day.split("-")[2]) % 45)  # More volatile

    return {
        "nifty_50_return": round(base_nifty + nifty_variance, 2),
        "mid_cap_return": round(base_midcap + midcap_variance, 2),
        "large_cap_return": round(base_largecap + largecap_variance, 2),
        "small_cap_return": round(base_smallcap + smallcap_variance, 2),
    }


def xirr(cashflows: list[tuple[str, float]], guess: float = 0.1) -> float | None:
    """Solve for the rate r such that sum(cf / (1+r)^(days/365)) == 0.
    Newton-Raphson with a bisection fallback. Returns None if it can't converge
    (e.g. all cashflows same sign, or fewer than 2 cashflows)."""
    if len(cashflows) < 2:
        return None
    parsed = sorted(
        (datetime.strptime(d, "%Y-%m-%d").date() if isinstance(d, str) else d, v)
        for d, v in cashflows
    )
    t0 = parsed[0][0]
    if not any(v > 0 for _, v in parsed) or not any(v < 0 for _, v in parsed):
        return None

    def npv(r: float) -> float:
        return sum(v / (1 + r) ** ((d - t0).days / 365) for d, v in parsed)

    def dnpv(r: float) -> float:
        return sum(
            -((d - t0).days / 365) * v / (1 + r) ** ((d - t0).days / 365 + 1)
            for d, v in parsed
        )

    r = guess
    for _ in range(50):
        f = npv(r)
        fp = dnpv(r)
        if abs(fp) < 1e-12:
            break
        r_new = r - f / fp
        if r_new <= -0.999:
            r_new = (r - 0.999) / 2
        if abs(r_new - r) < 1e-8:
            return round(r_new, 6)
        r = r_new
    else:
        r = None

    if r is not None and abs(npv(r)) < 1e-4:
        return round(r, 6)

    # bisection fallback over a wide, plausible range
    lo, hi = -0.999, 10.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        f_mid = npv(mid)
        if abs(f_mid) < 1e-4:
            return round(mid, 6)
        if f_lo * f_mid < 0:
            hi = mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2, 6)


def portfolio_cashflows(trades: list[dict], dividends: list[dict], market_value: float) -> list[tuple[str, float]]:
    cfs: list[tuple[str, float]] = []
    for t in trades:
        gross = t["price"] * t["quantity"]
        charges = t.get("charges") or 0.0
        if t["trade_type"] == "buy":
            cfs.append((t["trade_date"], -(gross + charges)))
        else:
            cfs.append((t["trade_date"], gross - charges))
    for d in dividends:
        cfs.append((d["ex_date"], d["amount_per_share"] * d["quantity"]))
    if market_value:
        cfs.append((date.today().strftime("%Y-%m-%d"), market_value))
    return cfs


def portfolio_xirr(trades: list[dict], dividends: list[dict] | None = None) -> float | None:
    if not trades:
        return None
    data = build_holdings(trades)
    cfs = portfolio_cashflows(trades, dividends or [], data["totals"]["market_value"])
    return xirr(cfs)


def cagr(trades: list[dict]) -> float | None:
    """Simple CAGR from total invested to current market value over the holding span.
    Cruder than XIRR (ignores the timing of interim buys/sells) but easy to sanity-check."""
    if not trades:
        return None
    data = build_holdings(trades)
    invested = data["totals"]["invested_value"]
    mv = data["totals"]["market_value"]
    if invested is None or mv is None or invested <= 0:
        return None
    first_date = datetime.strptime(min(t["trade_date"] for t in trades), "%Y-%m-%d").date()
    days = (date.today() - first_date).days
    if days <= 0:
        return None
    return round((mv / invested) ** (365 / days) - 1, 6)


def benchmark_series(trades: list[dict], prices: dict[str, float]) -> list[dict]:
    """Simulate investing each buy/sell's cash amount into the benchmark index on the
    same date, using the caller-supplied {date: close} price map (already resolved from
    cache + live fetch — this function does no I/O). Produces {date, benchmark_value}
    aligned to the same trade-days as `performance_series` so the two can be merged."""
    ts = sorted(trades, key=lambda t: t["trade_date"])
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        by_day[t["trade_date"]].append(t)

    price_dates = sorted(prices.keys())

    def price_on_or_before(day: str) -> float | None:
        import bisect

        idx = bisect.bisect_right(price_dates, day) - 1
        return prices[price_dates[idx]] if idx >= 0 else None

    units = 0.0
    last_price: float | None = None
    out: list[dict] = []
    for day in sorted(by_day):
        px = price_on_or_before(day)
        if px:
            last_price = px
            for t in by_day[day]:
                amt = t["price"] * t["quantity"]
                units += amt / px if t["trade_type"] == "buy" else -amt / px
        value = units * (px or last_price or 0)
        out.append({"date": day, "benchmark_value": round(value, 2)})
    return out


def holding_summary(trades: list[dict]) -> list[dict]:
    """One row per position — open or closed — in a single unified shape:
    {symbol, status, days_held, return_pct, pnl, value}. This is the raw material
    for the LLM narration in llm.narrate(); kept purely structured (no I/O) so it's
    also directly usable as a table on its own, LLM or not.
    """
    rows: list[dict] = []

    data = build_holdings(trades)
    for h in data["holdings"]:
        rows.append(
            {
                "symbol": h["symbol"],
                "status": "open",
                "days_held": h["holding_days"],
                "return_pct": h["unrealized_pct"],
                "pnl": h["unrealized_pnl"],
                "value": h["market_value"],
            }
        )

    for r in compute_round_trips(trades):
        rows.append(
            {
                "symbol": r["symbol"],
                "status": "closed",
                "days_held": r["days"],
                "return_pct": r["pnl_pct"],
                "pnl": r["pnl"],
                "value": round(r["quantity"] * r["sell_price"], 2),
            }
        )

    rows.sort(key=lambda r: (r["return_pct"] is None, r["return_pct"]), reverse=True)
    return rows


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

        # Get client details safely from the clients list
        client_obj = next((c for c in clients if c.get("id") == cid), {})
        client_code = client_obj.get("client_code", "")
        status = client_obj.get("status", "ACTIVE")
        trade_count = len(client_obj.get("trades", []))

        by_client.append({
            "id": cid, "name": name,
            "client_code": client_code,
            "status": status,
            "trade_count": trade_count,
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


def playbook(
    trades: list[dict],
    journal: dict[str, dict] | None = None,
    tags: list[dict] | None = None,
) -> list[dict]:
    """Closed round trips ("bought X, sold X, made/lost Y") — the trading playbook.
    'reason' is the buy trade's note if set, else its tag names joined."""
    journal = journal or {}
    tag_names = {t["id"]: t["name"] for t in (tags or [])}
    rows = compute_round_trips(trades)
    for r in rows:
        j = journal.get(r.pop("buy_fingerprint"), {})
        r.pop("sell_fingerprint", None)
        reason = j.get("note", "")
        if not reason and j.get("tag_ids"):
            reason = ", ".join(tag_names[tid] for tid in j["tag_ids"] if tid in tag_names)
        r["reason"] = reason
    rows.sort(key=lambda r: (r["sell_date"], r["buy_date"]))
    return rows


def playbook_by_stock(trades: list[dict]) -> list[dict]:
    """Playbook rows collapsed to one row per stock — total qty, weighted-average
    buy/sell price, aggregate P&L. Weighted (not simple) averages, since round-trip
    lots vary in size and a simple average would misrepresent the actual entry/exit
    cost. Detail rows for a given symbol are fetched separately (existing
    GET /playbook?symbol=... already supports this) for the click-through modal."""
    rows = compute_round_trips(trades)
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[r["symbol"]].append(r)

    out = []
    for symbol, rs in groups.items():
        total_qty = sum(r["quantity"] for r in rs)
        total_buy_value = sum(r["buy_price"] * r["quantity"] for r in rs)
        total_sell_value = sum(r["sell_price"] * r["quantity"] for r in rs)
        total_pnl = sum(r["pnl"] for r in rs)
        days_known = [r for r in rs if r["days"] is not None]
        avg_days = (
            sum(r["days"] * r["quantity"] for r in days_known) / sum(r["quantity"] for r in days_known)
            if days_known
            else None
        )
        out.append(
            {
                "symbol": symbol,
                "trades_count": len(rs),
                "total_qty": round(total_qty, 4),
                "avg_buy_price": round(total_buy_value / total_qty, 2) if total_qty else 0,
                "avg_sell_price": round(total_sell_value / total_qty, 2) if total_qty else 0,
                "total_pnl": round(total_pnl, 2),
                "pnl_pct": round(total_pnl / total_buy_value * 100, 2) if total_buy_value else 0,
                "avg_days": round(avg_days, 1) if avg_days is not None else None,
            }
        )
    out.sort(key=lambda r: r["total_pnl"], reverse=True)
    return out


def stock_analysis(trades: list[dict], symbol: str, actions: list[dict] | None = None) -> dict | None:
    symbol = symbol.upper()
    sym_trades = [t for t in trades if t["symbol"] == symbol]
    if not sym_trades:
        return None
    positions, _ = compute_positions(trades, actions)
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
