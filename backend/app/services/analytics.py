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

    # Calculate Sharpe Ratio (risk-adjusted returns)
    sharpe = calculate_sharpe_ratio(trades, risk_free_rate=0.06)  # 6% risk-free rate for India

    return {
        **t,
        "total_trades": len(trades),
        "buy_trades": buys,
        "sell_trades": sells,
        "first_trade_date": first_date,
        "last_trade_date": last_date,
        "initial_capital": round(initial_capital, 2),
        "current_invested": round(current_invested, 2),
        "sharpe_ratio": sharpe,  # Risk-adjusted returns metric
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
    `total_value` (invested + realized, in rupees) is the portfolio line callers plot;
    `portfolio_return` is the same thing indexed to 100 at the first day, kept for any
    caller that wants a normalized return rather than an absolute rupee curve. Benchmark
    comparison values are computed separately in benchmark_series() from real index prices
    and merged in by the router — this function has no benchmark data of its own.
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

        cumulative.append(
            {
                "date": day,
                "invested_value": round(invested, 2),
                "realized_pnl": round(realized, 2),
                # Cost-basis fallback — the router overwrites this with true mark-to-market
                # from market_value_series() whenever historical prices are available. Kept
                # as a fallback so the chart still renders (understating gains) if a price
                # fetch fails, rather than showing nothing.
                "total_value": round(total_value, 2),
                "portfolio_return": portfolio_return,
            }
        )
    return cumulative


def market_value_series(
    trades: list[dict], price_maps: dict[str, dict[str, float]], actions: list[dict] | None = None
) -> list[dict]:
    """True mark-to-market portfolio value over time: for each day, values every open
    position at that day's actual historical close (not cost basis), using the
    caller-supplied per-symbol {date: close} maps (already resolved from cache + live
    fetch — this function does no I/O, mirroring benchmark_series()). This is what makes
    the 'Your Portfolio' line on the Performance chart a real value curve — comparable to
    the benchmark lines — instead of a deployed-capital curve that only moves on buys/sells
    and silently omits unrealized gains on stocks still held.
    Falls back to a position's average cost for any day its price history doesn't cover
    (e.g. a very recently listed symbol), rather than dropping that position's value."""
    import bisect

    ts = sorted(trades, key=lambda t: t["trade_date"])
    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in ts:
        by_day[t["trade_date"]].append(t)

    sorted_dates = {sym: sorted(pm.keys()) for sym, pm in price_maps.items()}

    def price_on_or_before(symbol: str, day: str) -> float | None:
        dates = sorted_dates.get(symbol)
        if not dates:
            return None
        idx = bisect.bisect_right(dates, day) - 1
        return price_maps[symbol][dates[idx]] if idx >= 0 else None

    running: list[dict] = []
    out: list[dict] = []
    for day in sorted(by_day):
        running.extend(by_day[day])
        positions, realized = compute_positions(running, actions=actions or [])
        market_value = 0.0
        for p in positions:
            if p.quantity <= 0:
                continue
            px = price_on_or_before(p.symbol, day)
            market_value += p.quantity * (px if px is not None else p.avg_cost)
        out.append({"date": day, "market_value": round(market_value + realized, 2)})
    return out


_BOOK_VALUE_KEYS = [
    "invested_value", "realized_pnl", "total_value",
    "nifty_50_value", "mid_cap_value", "large_cap_value", "small_cap_value",
]


def aggregate_performance_series(client_series_list: list[list[dict]]) -> list[dict]:
    """Combine multiple clients' performance_series (each already real/mark-to-market,
    from compute_performance_series) into one book-level series — the manager's overall
    portfolio vs. Nifty/Midcap/etc. Summed at the VALUE level, aligned by calendar date
    with forward-fill: on any date a given client has no row of its own, its last-known
    value carries forward into the sum, so book value doesn't drop when one client is
    between trades while others aren't. Does NOT re-run FIFO across clients — that would
    incorrectly net one client's buy against another's sell of the same symbol; each
    client's own curve is trusted as-is and only summed.
    """
    import bisect

    if not client_series_list:
        return []

    all_dates = sorted({row["date"] for series in client_series_list for row in series})
    per_client_sorted = [sorted(series, key=lambda r: r["date"]) for series in client_series_list]
    per_client_dates = [[r["date"] for r in s] for s in per_client_sorted]

    out: list[dict] = []
    for day in all_dates:
        summed = {k: 0.0 for k in _BOOK_VALUE_KEYS}
        seen = {k: False for k in _BOOK_VALUE_KEYS}
        for rows, dates in zip(per_client_sorted, per_client_dates):
            idx = bisect.bisect_right(dates, day) - 1
            if idx < 0:
                continue  # this client hadn't started trading yet as of this date
            row = rows[idx]
            for k in _BOOK_VALUE_KEYS:
                v = row.get(k)
                if v is not None:
                    summed[k] += v
                    seen[k] = True
        entry = {"date": day}
        for k in _BOOK_VALUE_KEYS:
            entry[k] = round(summed[k], 2) if seen[k] else None
        out.append(entry)
    return out


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
    """CAGR from total invested to current portfolio value (market value + realized P&L).
    Period is from first trade date to today."""
    if not trades:
        return None
    data = build_holdings(trades)
    invested = data["totals"]["invested_value"]
    mv = data["totals"]["market_value"]
    realized_pnl = data["totals"]["realized_pnl"]

    # Ending value = current market value + realized P&L from closed positions
    ending_value = mv + realized_pnl

    if invested is None or ending_value is None or invested <= 0:
        return None
    first_date = datetime.strptime(min(t["trade_date"] for t in trades), "%Y-%m-%d").date()
    days = (date.today() - first_date).days
    if days <= 0:
        return None
    years = days / 365.25
    return round((ending_value / invested) ** (1 / years) - 1, 6)


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


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Core Performance Analytics
# ─────────────────────────────────────────────────────────────────────────────

def calculate_cagr(performance_series: list[dict]) -> float | None:
    """Compound Annual Growth Rate by annualizing the total portfolio return.
    Formula: (1 + Total Return %) ^ (1/Years) - 1
    Returns: CAGR as decimal (e.g., 0.1973 = 19.73%)
    """
    if not performance_series or len(performance_series) < 2:
        return None

    last = performance_series[-1]

    # Get actual invested and realized P&L (core metrics that are reliable)
    last_invested = last.get("invested_value", 0)
    last_realized_pnl = last.get("realized_pnl", 0)

    # Calculate current unrealized P&L from total_value
    # total_value = invested_value + realized_pnl + unrealized_pnl
    last_total_value = last.get("total_value", 0)
    last_unrealized_pnl = last_total_value - last_invested - last_realized_pnl if last_total_value else 0

    last_total_pnl = last_realized_pnl + last_unrealized_pnl

    if not last_invested or last_invested <= 0:
        return None

    from datetime import datetime
    first = performance_series[0]
    start_date = datetime.strptime(first["date"], "%Y-%m-%d").date()
    end_date = datetime.strptime(last["date"], "%Y-%m-%d").date()

    days = (end_date - start_date).days
    if days <= 0:
        return None

    years = days / 365.25

    # Total return percentage: total_pnl / invested_value
    total_return_pct = last_total_pnl / last_invested if last_invested > 0 else 0

    # CAGR = (1 + Total Return %) ^ (1/Years) - 1
    cagr = (1 + total_return_pct) ** (1 / years) - 1
    return cagr


def calculate_daily_returns(performance_series: list[dict]) -> list[float]:
    """Calculate daily portfolio returns from performance series.
    Returns: List of daily returns as decimals (e.g., 0.02 = 2% gain)
    """
    if not performance_series or len(performance_series) < 2:
        return []

    returns = []
    for i in range(1, len(performance_series)):
        prev_value = performance_series[i-1].get("total_value")
        curr_value = performance_series[i].get("total_value")

        if prev_value and prev_value > 0 and curr_value:
            daily_return = (curr_value - prev_value) / prev_value
            returns.append(daily_return)

    return returns


def calculate_volatility(performance_series: list[dict]) -> float | None:
    """Annual volatility (standard deviation of daily returns, annualized).
    Returns: Volatility as decimal (e.g., 0.185 = 18.5%)
    """
    daily_returns = calculate_daily_returns(performance_series)

    if len(daily_returns) < 2:
        return None

    import statistics
    std_dev = statistics.stdev(daily_returns)

    # Annualize: sqrt(252) trading days per year
    annual_volatility = std_dev * (252 ** 0.5)
    return annual_volatility


def calculate_max_drawdown(performance_series: list[dict]) -> float | None:
    """Maximum drawdown: worst peak-to-trough loss.
    Returns: Max drawdown as decimal (e.g., -0.234 = -23.4%)
    """
    if not performance_series:
        return None

    max_drawdown = 0.0
    peak_value = 0.0

    for entry in performance_series:
        value = entry.get("total_value")
        if value is None:
            continue

        if value > peak_value:
            peak_value = value

        if peak_value > 0:
            drawdown = (value - peak_value) / peak_value
            if drawdown < max_drawdown:
                max_drawdown = drawdown

    return max_drawdown if max_drawdown < 0 else None


def calculate_current_drawdown(performance_series: list[dict]) -> float | None:
    """Current drawdown from recent peak.
    Returns: Current drawdown as decimal (e.g., -0.082 = -8.2%)
    """
    if not performance_series:
        return None

    current_value = performance_series[-1].get("total_value")
    if current_value is None or current_value <= 0:
        return None

    peak_value = 0.0
    for entry in performance_series:
        value = entry.get("total_value")
        if value and value > peak_value:
            peak_value = value

    if peak_value > 0:
        return (current_value - peak_value) / peak_value

    return None


def calculate_sharpe_ratio(performance_series: list[dict], risk_free_rate: float = 0.065) -> float | None:
    """Sharpe Ratio: (Portfolio Return - Risk-Free Rate) / Volatility
    Args:
        performance_series: Portfolio performance over time
        risk_free_rate: Annual risk-free rate (default 6.5% = RBI repo rate)
    Returns: Sharpe ratio as decimal (e.g., 1.85)
    """
    cagr = calculate_cagr(performance_series)
    volatility = calculate_volatility(performance_series)

    if cagr is None or volatility is None or volatility == 0:
        return None

    sharpe = (cagr - risk_free_rate) / volatility
    return sharpe


def calculate_benchmark_cagr(benchmark_series: list[dict]) -> float | None:
    """Calculate CAGR for benchmark performance series (same as portfolio CAGR)."""
    return calculate_cagr(benchmark_series)


def calculate_beta(portfolio_returns: list[float], benchmark_returns: list[float]) -> float | None:
    """Beta: Covariance(portfolio, benchmark) / Variance(benchmark)
    How much portfolio moves relative to benchmark (e.g., beta=1.2 = 20% more volatile)
    Args:
        portfolio_returns: Daily returns from performance series
        benchmark_returns: Daily returns from benchmark series
    Returns: Beta as decimal (e.g., 1.15)
    """
    if not portfolio_returns or not benchmark_returns:
        return None

    if len(portfolio_returns) != len(benchmark_returns):
        # Align to shorter length
        min_len = min(len(portfolio_returns), len(benchmark_returns))
        portfolio_returns = portfolio_returns[-min_len:]
        benchmark_returns = benchmark_returns[-min_len:]

    if len(portfolio_returns) < 2:
        return None

    import statistics

    # Calculate means
    port_mean = statistics.mean(portfolio_returns)
    bench_mean = statistics.mean(benchmark_returns)

    # Calculate covariance
    covariance = sum(
        (portfolio_returns[i] - port_mean) * (benchmark_returns[i] - bench_mean)
        for i in range(len(portfolio_returns))
    ) / len(portfolio_returns)

    # Calculate benchmark variance
    bench_variance = sum(
        (b - bench_mean) ** 2
        for b in benchmark_returns
    ) / len(benchmark_returns)

    if bench_variance == 0:
        return None

    beta = covariance / bench_variance
    return beta


def calculate_alpha(cagr: float, benchmark_cagr: float, beta: float,
                   risk_free_rate: float = 0.065) -> float | None:
    """Alpha: Excess return vs benchmark (adjusted for risk via Beta)
    Formula: Portfolio Return - (Risk-Free Rate + Beta * (Benchmark Return - Risk-Free Rate))
    Returns: Alpha as decimal (e.g., 0.052 = +5.2%)
    """
    if cagr is None or benchmark_cagr is None or beta is None:
        return None

    expected_return = risk_free_rate + beta * (benchmark_cagr - risk_free_rate)
    alpha = cagr - expected_return
    return alpha


def compute_performance_metrics(performance_series: list[dict],
                               benchmark_performance: list[dict] | None = None,
                               risk_free_rate: float = 0.065) -> dict:
    """Compute all Phase 1 performance metrics at once.
    Args:
        performance_series: Portfolio performance history
        benchmark_performance: Benchmark performance history (if available)
        risk_free_rate: Annual risk-free rate (default 6.5%)
    Returns: Dictionary with all metrics
    """
    if not performance_series:
        return {}

    portfolio_cagr = calculate_cagr(performance_series)
    portfolio_volatility = calculate_volatility(performance_series)
    sharpe = calculate_sharpe_ratio(performance_series, risk_free_rate)
    max_drawdown = calculate_max_drawdown(performance_series)
    current_drawdown = calculate_current_drawdown(performance_series)

    # Calculate portfolio daily returns for beta calculation
    portfolio_returns = calculate_daily_returns(performance_series)

    # Calculate beta and alpha if benchmark available
    beta = None
    alpha = None
    benchmark_cagr = None

    if benchmark_performance and len(benchmark_performance) >= 2:
        benchmark_cagr = calculate_benchmark_cagr(benchmark_performance)
        benchmark_returns = calculate_daily_returns(benchmark_performance)

        if benchmark_returns:
            beta = calculate_beta(portfolio_returns, benchmark_returns)
            if beta is not None and benchmark_cagr is not None:
                alpha = calculate_alpha(portfolio_cagr, benchmark_cagr, beta, risk_free_rate)

    # Time period calculation
    from datetime import datetime
    start_date = None
    end_date = None

    if performance_series:
        start_date = datetime.strptime(performance_series[0]["date"], "%Y-%m-%d").date()
        end_date = datetime.strptime(performance_series[-1]["date"], "%Y-%m-%d").date()

    days_held = (end_date - start_date).days if start_date and end_date else None

    return {
        "cagr": round(portfolio_cagr, 4) if portfolio_cagr is not None else None,
        "volatility": round(portfolio_volatility, 4) if portfolio_volatility is not None else None,
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "max_drawdown": round(max_drawdown, 4) if max_drawdown is not None else None,
        "current_drawdown": round(current_drawdown, 4) if current_drawdown is not None else None,
        "beta": round(beta, 4) if beta is not None else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "benchmark_cagr": round(benchmark_cagr, 4) if benchmark_cagr is not None else None,
        "days_held": days_held,
        "start_date": str(start_date) if start_date else None,
        "end_date": str(end_date) if end_date else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Performance Attribution
# ─────────────────────────────────────────────────────────────────────────────

def calculate_sector_pnl(trades: list[dict]) -> dict[str, dict]:
    """Calculate P&L contribution by sector.
    Returns: {sector: {symbol: pnl_amount, ...}, ...}
    """
    from app.services.engine import compute_round_trips
    from app.services.securities import classify

    round_trips = compute_round_trips(trades)
    sector_pnl = defaultdict(lambda: defaultdict(float))

    for rt in round_trips:
        symbol = rt["symbol"]
        pnl = rt.get("pnl", 0)  # Key field from compute_round_trips
        meta = classify(symbol)
        sector = meta.get("sector", "Unclassified")

        sector_pnl[sector][symbol] += pnl

    return {sector: dict(stocks) for sector, stocks in sector_pnl.items()}


def calculate_sector_contribution(trades: list[dict]) -> dict:
    """Calculate contribution of each sector to total portfolio returns.
    Returns: {sector: {pnl: amount, contribution_pct: %}, ...}
    """
    from app.services.securities import classify

    sector_pnl = calculate_sector_pnl(trades)
    total_pnl = sum(
        sum(stocks.values()) for stocks in sector_pnl.values()
    )

    if total_pnl == 0:
        return {}

    contributions = {}
    for sector, stocks in sector_pnl.items():
        sector_total = sum(stocks.values())
        contributions[sector] = {
            "pnl": round(sector_total, 2),
            "contribution_pct": round((sector_total / total_pnl) * 100, 2),
            "num_stocks": len(stocks),
            "num_trades": sum(1 for t in trades if classify(t["symbol"]).get("sector") == sector),
        }

    return contributions


def calculate_stock_contribution(trades: list[dict]) -> dict:
    """Calculate P&L contribution of each stock to total returns.
    Returns: {symbol: {pnl: amount, contribution_pct: %, sector: sector, ...}, ...}
    """
    from app.services.engine import compute_round_trips
    from app.services.securities import classify

    round_trips = compute_round_trips(trades)
    total_pnl = sum(rt.get("pnl", 0) for rt in round_trips)

    if total_pnl == 0:
        return {}

    contributions = {}
    for rt in round_trips:
        symbol = rt["symbol"]
        pnl = rt.get("pnl", 0)
        meta = classify(symbol)

        contributions[symbol] = {
            "pnl": round(pnl, 2),
            "contribution_pct": round((pnl / total_pnl) * 100, 2),
            "sector": meta.get("sector", "Unclassified"),
            "num_trades": sum(1 for t in trades if t["symbol"] == symbol),
            "buy_price": rt.get("buy_price"),
            "sell_price": rt.get("sell_price"),
        }

    return contributions


def calculate_sector_vs_stock_attribution(performance_series: list[dict],
                                        trades: list[dict]) -> dict:
    """Decompose returns into sector selection vs stock selection.

    This is a simplified attribution that answers:
    - How much return came from being overweight in good sectors?
    - How much came from picking better stocks within sectors?

    Returns: {sector_selection_pct: %, stock_selection_pct: %, details: {...}}
    """
    sector_contrib = calculate_sector_contribution(trades)

    if not sector_contrib:
        return {
            "sector_selection_pct": 0,
            "stock_selection_pct": 0,
            "details": "No closed positions to analyze"
        }

    # Simple heuristic:
    # - Sectors with high concentration (top 3) = sector selection skill
    # - Sector diversification = stock selection skill
    sorted_sectors = sorted(
        sector_contrib.items(),
        key=lambda x: abs(x[1]["pnl"]),
        reverse=True
    )

    # If concentrated in few sectors with big wins = sector selection
    # If diversified with many small wins = stock selection
    top_3_pnl = sum(sector[1]["pnl"] for sector in sorted_sectors[:3])
    total_pnl = sum(s[1]["pnl"] for s in sorted_sectors)

    if total_pnl == 0:
        return {
            "sector_selection_pct": 0,
            "stock_selection_pct": 0,
            "top_performing_sectors": []
        }

    # Rough split: top 3 sectors = sector selection, rest = stock selection
    sector_selection = (top_3_pnl / total_pnl) * 100
    stock_selection = 100 - sector_selection

    return {
        "sector_selection_pct": round(sector_selection, 2),
        "stock_selection_pct": round(stock_selection, 2),
        "top_performing_sectors": [
            {
                "sector": s[0],
                "pnl": s[1]["pnl"],
                "contribution_pct": s[1]["contribution_pct"],
                "num_stocks": s[1]["num_stocks"],
            }
            for s in sorted_sectors[:5]
        ],
        "total_pnl": round(total_pnl, 2),
    }


def build_attribution_waterfall(trades: list[dict]) -> list[dict]:
    """Build waterfall data: Starting capital → Sector decisions → Stock selection → Final return.

    Returns: List of waterfall entries for visualization
    [
        {name: "Starting Capital", value: capital, type: "base"},
        {name: "Healthcare Picks", value: 15000, type: "sector"},
        {name: "Tech Picks", value: -5000, type: "sector"},
        ...
        {name: "Stock Selection", value: 10000, type: "selection"},
        {name: "Final P&L", value: 45000, type: "total"}
    ]
    """
    sector_contrib = calculate_sector_contribution(trades)

    if not sector_contrib:
        return []

    waterfall = []

    # Start
    invested = sum(t.get("trade_value", 0) for t in trades if t.get("trade_type") == "buy")
    waterfall.append({"name": "Invested Capital", "value": invested, "type": "base"})

    # Add sectors (only winners for positive, losers separately)
    positive_sectors = [(s, c) for s, c in sector_contrib.items() if c["pnl"] >= 0]
    negative_sectors = [(s, c) for s, c in sector_contrib.items() if c["pnl"] < 0]

    positive_sectors.sort(key=lambda x: x[1]["pnl"], reverse=True)
    negative_sectors.sort(key=lambda x: x[1]["pnl"])

    for sector, contrib in positive_sectors:
        waterfall.append({
            "name": f"{sector}",
            "value": contrib["pnl"],
            "type": "positive",
            "contribution_pct": contrib["contribution_pct"],
        })

    for sector, contrib in negative_sectors:
        waterfall.append({
            "name": f"{sector}",
            "value": contrib["pnl"],
            "type": "negative",
            "contribution_pct": contrib["contribution_pct"],
        })

    # Final total
    total_pnl = sum(c["pnl"] for c in sector_contrib.values())
    waterfall.append({
        "name": "Total P&L",
        "value": total_pnl,
        "type": "total"
    })

    return waterfall


def compute_attribution_metrics(performance_series: list[dict],
                               trades: list[dict]) -> dict:
    """Compute all Phase 2 attribution metrics at once."""
    sector_contrib = calculate_sector_contribution(trades)
    stock_contrib = calculate_stock_contribution(trades)
    sector_vs_stock = calculate_sector_vs_stock_attribution(performance_series, trades)
    waterfall = build_attribution_waterfall(trades)

    # Sort contributions
    top_stocks = sorted(
        stock_contrib.items(),
        key=lambda x: x[1]["pnl"],
        reverse=True
    )

    return {
        "by_sector": sector_contrib,
        "by_stock": stock_contrib,
        "sector_vs_stock": sector_vs_stock,
        "top_stocks": [
            {
                "symbol": s[0],
                "pnl": s[1]["pnl"],
                "contribution_pct": s[1]["contribution_pct"],
                "sector": s[1]["sector"],
                "num_trades": s[1]["num_trades"],
            }
            for s in top_stocks[:10]
        ],
        "worst_stocks": [
            {
                "symbol": s[0],
                "pnl": s[1]["pnl"],
                "contribution_pct": s[1]["contribution_pct"],
                "sector": s[1]["sector"],
                "num_trades": s[1]["num_trades"],
            }
            for s in top_stocks[-5:] if s[1]["pnl"] < 0
        ],
        "waterfall": waterfall,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Trade Analytics
# ─────────────────────────────────────────────────────────────────────────────

def compute_trade_analytics(trades: list[dict]) -> dict:
    """Phase 3: Trade quality metrics (win rate, profit factor, best/worst trades)."""
    from app.services.engine import compute_round_trips
    from app.services.securities import classify

    round_trips = compute_round_trips(trades)

    if not round_trips:
        return {"error": "No closed trades"}

    winning = [rt for rt in round_trips if rt.get("pnl", 0) > 0]
    losing = [rt for rt in round_trips if rt.get("pnl", 0) < 0]
    total_pnl = sum(rt.get("pnl", 0) for rt in round_trips)

    total_win = sum(rt.get("pnl", 0) for rt in winning) if winning else 0
    total_loss = abs(sum(rt.get("pnl", 0) for rt in losing)) if losing else 0

    # Win rate by sector. classify() can do a per-symbol network lookup, so resolve each
    # DISTINCT symbol once (3,000+ round trips collapse to a few hundred symbols) instead
    # of once per round trip — the difference between ~seconds and ~a minute.
    _sector_of: dict[str, str] = {}

    def _sec(sym: str) -> str:
        if sym not in _sector_of:
            _sector_of[sym] = classify(sym).get("sector", "Unclassified")
        return _sector_of[sym]

    by_sector = defaultdict(lambda: {"win": 0, "loss": 0})
    for rt in round_trips:
        sector = _sec(rt["symbol"])
        if rt.get("pnl", 0) > 0:
            by_sector[sector]["win"] += 1
        else:
            by_sector[sector]["loss"] += 1

    sector_win_rates = {
        sector: round((data["win"] / (data["win"] + data["loss"]) * 100) if (data["win"] + data["loss"]) > 0 else 0, 1)
        for sector, data in by_sector.items()
    }

    # Sort best/worst
    sorted_rt = sorted(round_trips, key=lambda x: x.get("pnl", 0), reverse=True)

    def _tt(rt: dict) -> dict:
        return {"symbol": rt["symbol"], "pnl": rt.get("pnl", 0),
                "pnl_pct": rt.get("pnl_pct", 0), "days": rt.get("days", 0),
                "date": rt.get("sell_date", "")}

    # ── equity curve + drawdown: cumulative realised P&L by exit date ──
    by_exit = sorted(round_trips, key=lambda x: x.get("sell_date", ""))
    equity_curve, cum, peak = [], 0.0, 0.0
    for rt in by_exit:
        cum += rt.get("pnl", 0)
        peak = max(peak, cum)
        equity_curve.append({"date": rt.get("sell_date", ""), "cum_pnl": round(cum, 2),
                             "drawdown": round(cum - peak, 2)})

    # ── P&L distribution by return % ──
    _edges = [(-1e9, -20), (-20, -10), (-10, -5), (-5, 0),
              (0, 5), (5, 10), (10, 20), (20, 50), (50, 1e9)]
    _labels = ["<-20%", "-20/-10%", "-10/-5%", "-5/0%",
               "0/5%", "5/10%", "10/20%", "20/50%", ">50%"]
    distribution = []
    for (lo, hi), lab in zip(_edges, _labels):
        b = [rt for rt in round_trips if lo <= rt.get("pnl_pct", 0) < hi]
        distribution.append({"bucket": lab, "count": len(b),
                             "pnl": round(sum(rt.get("pnl", 0) for rt in b), 0)})

    # ── monthly P&L ──
    _mon: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for rt in round_trips:
        mkey = (rt.get("sell_date") or "")[:7]
        if not mkey:
            continue
        _mon[mkey]["pnl"] += rt.get("pnl", 0)
        _mon[mkey]["trades"] += 1
        if rt.get("pnl", 0) > 0:
            _mon[mkey]["wins"] += 1
    monthly_pnl = [{"month": k, "pnl": round(v["pnl"], 0), "trades": v["trades"],
                    "win_rate": round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0}
                   for k, v in sorted(_mon.items())]

    # ── win rate by exit weekday ──
    _wd: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "trades": 0, "wins": 0})
    for rt in round_trips:
        try:
            dow = date.fromisoformat((rt.get("sell_date") or "")[:10]).strftime("%a")
        except (ValueError, TypeError):
            continue
        _wd[dow]["pnl"] += rt.get("pnl", 0)
        _wd[dow]["trades"] += 1
        if rt.get("pnl", 0) > 0:
            _wd[dow]["wins"] += 1
    by_weekday = [{"day": d, "trades": _wd[d]["trades"], "pnl": round(_wd[d]["pnl"], 0),
                   "win_rate": round(_wd[d]["wins"] / _wd[d]["trades"] * 100, 1) if _wd[d]["trades"] else 0}
                  for d in ["Mon", "Tue", "Wed", "Thu", "Fri"] if _wd[d]["trades"]]

    # ── win rate by holding period ──
    _hb = [("Intraday", 0, 0), ("1-7d", 1, 7), ("8-30d", 8, 30),
           ("31-90d", 31, 90), ("90d+", 91, 10 ** 9)]
    by_holding = []
    for lab, lo, hi in _hb:
        b = [rt for rt in round_trips if lo <= rt.get("days", 0) <= hi]
        if not b:
            continue
        w = sum(1 for rt in b if rt.get("pnl", 0) > 0)
        by_holding.append({"bucket": lab, "trades": len(b),
                           "pnl": round(sum(rt.get("pnl", 0) for rt in b), 0),
                           "win_rate": round(w / len(b) * 100, 1)})

    total_wins_r = total_win
    expectancy = round((total_pnl / len(round_trips)), 2) if round_trips else 0

    return {
        "total_trades": len(round_trips),
        "winning_trades": len(winning),
        "losing_trades": len(losing),
        "win_rate": round((len(winning) / len(round_trips) * 100) if round_trips else 0, 1),
        "profit_factor": round(total_win / total_loss, 2) if total_loss > 0 else None,
        "avg_win": round(total_win / len(winning), 2) if winning else 0,
        "avg_loss": round(total_loss / len(losing), 2) if losing else 0,
        "expectancy": expectancy,
        "total_pnl": round(total_pnl, 2),
        "best_trade": {
            "symbol": sorted_rt[0]["symbol"],
            "pnl": sorted_rt[0].get("pnl", 0),
            "days": sorted_rt[0].get("days", 0),
        } if sorted_rt else None,
        "worst_trade": {
            "symbol": sorted_rt[-1]["symbol"],
            "pnl": sorted_rt[-1].get("pnl", 0),
            "days": sorted_rt[-1].get("days", 0),
        } if sorted_rt else None,
        "top_winners": [_tt(rt) for rt in sorted_rt[:5]],
        "top_losers": [_tt(rt) for rt in sorted_rt[::-1][:5]],
        "sector_win_rates": sector_win_rates,
        "avg_holding_days": round(sum(rt.get("days", 0) for rt in round_trips) / len(round_trips), 0) if round_trips else 0,
        "equity_curve": equity_curve,
        "distribution": distribution,
        "monthly_pnl": monthly_pnl,
        "by_weekday": by_weekday,
        "by_holding": by_holding,
    }


def compute_risk_monitoring(performance_series: list[dict], trades: list[dict]) -> dict:
    """Phase 4: Risk monitoring (concentration, correlation, health score)."""
    from app.services.engine import compute_positions
    from app.services.securities import classify

    if not performance_series:
        return {"error": "No data"}

    positions, _ = compute_positions(trades)
    open_pos = [p for p in positions if p.quantity > 0]

    if not open_pos:
        return {"error": "No open positions"}

    # Concentration (using invested_value)
    total_inv = sum(p.invested_value for p in open_pos if p.invested_value)

    # Top 10 concentration
    sorted_pos = sorted(open_pos, key=lambda p: p.invested_value or 0, reverse=True)
    top_10_pct = round((sum((p.invested_value or 0) for p in sorted_pos[:10]) / total_inv * 100) if total_inv else 0, 1)

    # Sector concentration
    by_sector = defaultdict(float)
    for p in open_pos:
        sector = classify(p.symbol).get("sector", "Unclassified")
        by_sector[sector] += (p.invested_value or 0)

    sector_pcts = {s: round((v / total_inv * 100), 1) for s, v in by_sector.items()} if total_inv else {}
    largest_sector = max(sector_pcts.items(), key=lambda x: x[1])[0] if sector_pcts else None
    largest_sector_pct = max(sector_pcts.values()) if sector_pcts else 0

    # Cap concentration
    by_cap = defaultdict(float)
    for p in open_pos:
        cap = classify(p.symbol).get("cap", "Unknown")
        by_cap[cap] += (p.invested_value or 0)

    cap_pcts = {c: round((v / total_inv * 100), 1) for c, v in by_cap.items()} if total_inv else {}

    # Health score (0-100)
    score = 100
    if top_10_pct > 70:
        score -= 20
    elif top_10_pct > 60:
        score -= 10
    if largest_sector_pct > 40:
        score -= 15
    elif largest_sector_pct > 30:
        score -= 5

    volatility = calculate_volatility(performance_series) or 0
    if volatility > 25:
        score -= 10
    elif volatility > 20:
        score -= 5

    max_dd = calculate_max_drawdown(performance_series) or 0
    if max_dd < -30:
        score -= 15
    elif max_dd < -20:
        score -= 10

    current_dd = calculate_current_drawdown(performance_series) or 0
    if current_dd < -15:
        score -= 10
    elif current_dd < -10:
        score -= 5

    score = max(0, min(100, score))

    return {
        "health_score": round(score),
        "concentration": {
            "top_10_pct": top_10_pct,
            "largest_sector": largest_sector,
            "largest_sector_pct": largest_sector_pct,
        },
        "by_sector": sector_pcts,
        "by_cap": cap_pcts,
        "total_positions": len(open_pos),
        "alerts": [a for a in [
            "High concentration" if top_10_pct > 70 else None,
            "Sector overweight" if largest_sector_pct > 40 else None,
            "High volatility" if volatility > 25 else None,
            "Deep drawdown" if max_dd < -30 else None,
        ] if a is not None]
    }


def calculate_sharpe_ratio(trades: list[dict], cash_flow_history: list[dict] | None = None,
                          risk_free_rate: float = 0.06) -> float | None:
    """Calculate Sharpe Ratio: (Return - Risk-Free Rate) / Volatility.

    Args:
        trades: all trades (buy/sell)
        cash_flow_history: list of {date, amount, type} for deposits/withdrawals
        risk_free_rate: annual risk-free rate (default 6% for India)

    Returns:
        Sharpe ratio (higher = better risk-adjusted returns), or None if insufficient data
    """
    if not trades:
        return None

    # Calculate portfolio values over time from trades
    from collections import defaultdict
    import statistics

    # Group trades by date
    trades_by_date = defaultdict(list)
    for t in trades:
        date_key = t.get("trade_date", "")
        if date_key:
            trades_by_date[date_key].append(t)

    if len(trades_by_date) < 30:
        return None  # Need at least 30 data points

    # Calculate daily portfolio values (simplified: sum of invested value)
    portfolio_values = []
    total_invested = 0.0
    total_realized = 0.0

    for date_key in sorted(trades_by_date.keys()):
        for trade in trades_by_date[date_key]:
            qty = trade.get("quantity", 0)
            price = trade.get("price", 0)
            action = trade.get("action", "")

            if action.upper() == "BUY":
                total_invested += qty * price
            elif action.upper() == "SELL":
                # For realized P&L (simplified)
                total_invested -= qty * price

        # Current portfolio value estimate
        portfolio_values.append(total_invested)

    if len(portfolio_values) < 30:
        return None

    # Calculate returns (daily percentage change)
    returns = []
    for i in range(1, len(portfolio_values)):
        if portfolio_values[i-1] != 0:
            daily_return = (portfolio_values[i] - portfolio_values[i-1]) / portfolio_values[i-1]
            returns.append(daily_return)

    if len(returns) < 30:
        return None

    # Calculate volatility (standard deviation of returns)
    try:
        volatility = statistics.stdev(returns)  # Daily volatility
    except:
        return None

    if volatility == 0:
        return None

    # Annualize returns and volatility (252 trading days/year)
    annual_volatility = volatility * (252 ** 0.5)
    avg_daily_return = sum(returns) / len(returns)
    annual_return = ((1 + avg_daily_return) ** 252) - 1

    # Calculate Sharpe Ratio
    excess_return = annual_return - risk_free_rate
    sharpe_ratio = excess_return / annual_volatility

    return round(sharpe_ratio, 2)
