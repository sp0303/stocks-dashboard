"""Portfolio analytics — assembles dashboard payloads from trades + live quotes + sectors.

Everything here is derived. The FIFO engine owns positions/realized P&L; this module layers
market valuation, allocation, concentration, performance series and per-stock analysis.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from app.services.engine import _num, compute_positions, compute_round_trips, matched_trades
from app.services.market_data import get_quotes
from app.services.securities import classify

#: Annual risk-free rate used by every risk-adjusted metric. One value, because Sharpe was
#: previously computed at 6% in the summary and 6.5% in the metrics endpoint, so the same
#: portfolio scored differently depending on which card you read. Roughly the RBI repo rate.
RISK_FREE_RATE = 0.065


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
        # A rights entitlement (NSE "-RE" series) is not a holding: it trades for a couple of
        # weeks, then converts into shares (bought separately) or lapses worthless. Its last
        # traded price keeps a lapsed entitlement on the books at a value nobody can realise,
        # so it is left unpriced (out of cost AND value, R6) and flagged for review (R8).
        rights = p.symbol.upper().endswith("-RE")
        ltp = None if rights else q.get("price")
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
                "rights_entitlement": rights,
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
            "invested_value": round(total_invested, 2),      # current investment (cost of holdings)
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


def peak_capital_deployed(trades: list[dict]) -> float:
    """The most of the investor's OWN money ever tied up at one time — the maximum of the
    running (cumulative buys - cumulative sells) cash outflow.

    This is what "Invested" means across the dashboard, and it is the denominator for
    return %. Two tempting alternatives are both wrong as a headline:

    * `buy_total - sell_total` (what this used to show as "Deployed Capital") is ending
      NET cash flow, not capital deployed. It shrinks as the investor takes money out and
      goes negative on a profitable account that recycles capital — e.g. 10L recycled four
      times at +20% reports -5.7L "deployed". It only looks right on an account that has
      accumulated monotonically and never withdrawn.
    * Gross bought double-counts recycled capital: a book that turns the same 1L over ten
      times reads as 10L invested, understating return tenfold.

    Peak outflow has neither failure mode: it never goes negative, and reinvested proceeds
    don't inflate it because the sell that funded the buy is netted off first.
    """
    if not trades:
        return 0.0
    # Net each DAY's flows before accumulating, rather than walking trade by trade. Within
    # a single session the order of fills is not a capital requirement: selling A and buying
    # B the same day is funded by the sale, not by new money. Walking trade-by-trade with
    # buys first would book a phantom spike — a book that rolls 10L from one stock to the
    # next each month would read as 22L of capital at risk instead of the 10L actually put in.
    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        gross = _num(t.get("price")) * _num(t.get("quantity"))
        charges = _num(t.get("charges"))
        if str(t.get("trade_type", "")).lower() == "buy":
            by_day[str(t.get("trade_date", ""))] += gross + charges
        else:
            by_day[str(t.get("trade_date", ""))] -= gross - charges

    running = peak = 0.0
    for day in sorted(by_day):
        running += by_day[day]
        peak = max(peak, running)
    return round(peak, 2)


def portfolio_summary(trades: list[dict], actions: list[dict] | None = None) -> dict:
    data = build_holdings(trades, actions=actions)
    t = data["totals"]
    buys = sum(1 for x in trades if x["trade_type"] == "buy")
    sells = len(trades) - buys

    first_date = min((t["trade_date"] for t in trades), default=None) if trades else None
    last_date = max((t["trade_date"] for t in trades), default=None) if trades else None
    buy_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "buy")
    sell_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "sell")

    # "Invested" headline = peak capital at risk. See peak_capital_deployed() for why the
    # old `buy_total - sell_total` is not capital deployed (it can go negative).
    peak_capital = peak_capital_deployed(matched_trades(trades, actions))

    # Current invested = cost basis of currently held positions. Kept as its own figure
    # (it's what a broker's holdings screen shows) but NOT the return denominator: once
    # realized gains are reinvested it exceeds the cash ever put in, which is exactly how
    # a 10.0% return came to display as 9.1%.
    current_invested = t["invested_value"]

    total_pnl = t["total_pnl"]

    return {
        **t,
        # Override the holdings-scoped return_pct from build_holdings, which divides by
        # open cost basis and so inflates returns on any book with closed trades.
        "return_pct": round(total_pnl / peak_capital * 100, 2) if peak_capital else 0.0,
        "total_trades": len(trades),
        "buy_trades": buys,
        "sell_trades": sells,
        "first_trade_date": first_date,
        "last_trade_date": last_date,
        "peak_capital": peak_capital,
        "gross_bought": round(buy_total, 2),
        "gross_sold": round(sell_total, 2),
        # Retained so existing callers don't KeyError; superseded by peak_capital.
        "initial_capital": round(buy_total - sell_total, 2),
        "current_invested": round(current_invested, 2),
        # Sharpe needs the time-weighted NAV curve, which needs historical prices, which
        # this synchronous summary has no business fetching. It is served by /metrics,
        # which is where the UI reads it from.
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

        # Closed positions, valued at the PEAK capital each symbol ever required rather
        # than the sum of every round trip's buy leg. Summing the legs counts recycled
        # money once per cycle: a symbol traded 11 times contributed 11 separate buys to
        # its own weight, so the names churned most looked like the largest bets when they
        # may never have held more than a small position at a time.
        by_symbol: dict[str, list[dict]] = defaultdict(list)
        for t in trades:
            by_symbol[t["symbol"]].append(t)

        open_symbols = {h["symbol"] for h in data["holdings"]}
        for sym, sym_trades in by_symbol.items():
            if sym in open_symbols:
                continue  # already counted above at its open cost basis
            peak = peak_capital_deployed(sym_trades)
            if peak <= 0:
                continue
            m = classify(sym)
            key = {
                "sector": m["sector"], "asset": m["asset_class"], "stock": sym, "cap": m["cap"],
            }.get(by, m["sector"])
            buckets[key] += peak
            total += peak

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


def daily_performance_series(
    trades: list[dict],
    calendar: list[str],
    price_maps: dict[str, dict[str, float]] | None = None,
    actions: list[dict] | None = None,
) -> list[dict]:
    """Mark-to-market portfolio value for EVERY day in `calendar`, not just trade days.

    The series this replaces emitted one row per day the client traded, which on a real
    book meant a chart with almost no data in it — a typical account had 15 points across
    191 calendar days (7.9% coverage) with single straight lines drawn across gaps of up
    to 48 days. Every metric derived from it (volatility, drawdown, beta, Sharpe) was being
    computed on those 15 points and then annualised as though they were consecutive days.

    `calendar` is the trading calendar to sample on — pass the benchmark index's own price
    dates, which are exactly the days NSE was open. Trade dates are always included even if
    the index map lacks them.

    Positions are re-derived only on days the book actually changed; every other day reuses
    the most recent snapshot and re-values it at that day's close. So cost stays O(trade
    days x trades) as before, and the extra daily resolution costs only a valuation pass.

    Each row carries:
      invested_value  cost basis of open positions
      realized_pnl    cumulative realised, from closed quantity
      net_invested    cumulative cash actually put in (buys - sells)
      market_value    mark-to-market value of open positions
      total_value     market_value + realized_pnl (the historical key, kept for callers)
      pnl             market_value - net_invested == realised + unrealised

    `pnl` is the figure to plot. It shares a baseline with the benchmark lines (see
    benchmark_series), so portfolio and index are finally measured the same way.
    """
    import bisect

    if not trades:
        return []

    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_day[str(t["trade_date"])].append(t)
    trade_days = sorted(by_day)

    price_maps = price_maps or {}
    sorted_px = {sym: sorted(pm) for sym, pm in price_maps.items()}

    def price_on_or_before(symbol: str, day: str) -> float | None:
        dates = sorted_px.get(symbol)
        if not dates:
            return None
        idx = bisect.bisect_right(dates, day) - 1
        return price_maps[symbol][dates[idx]] if idx >= 0 else None

    def price_on_or_after(symbol: str, day: str) -> float | None:
        dates = sorted_px.get(symbol)
        if not dates:
            return None
        idx = bisect.bisect_left(dates, day)
        return price_maps[symbol][dates[idx]] if idx < len(dates) else None

    # Price basis (R17). Trades are as-traded, but the history may be split-adjusted, and
    # the engine applies every known split/bonus to the snapshot quantities up front. So a
    # stock bought at 429 can sit next to a history close of 86 (an adjusted 1:5 split the
    # corporate-action feed never reported): valued at 86 the buy books an instant -80% day,
    # and on one real account those days compounded into a -64% TWR on a book that had made
    # +7L. On each trade day we measure the stock's trade price against its close, in the
    # snapshot's (post-known-actions) units; a gap beyond normal intraday range is a basis
    # difference, and the history is rescaled by it until the stock next trades.
    split_events: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for a in actions or []:
        mult = _num(a.get("qty_multiplier")) or 1.0
        if a.get("type") in ("SPLIT", "BONUS") and a.get("ex_date") and mult != 1.0:
            split_events[str(a.get("symbol") or "")].append((str(a["ex_date"]), mult))

    def future_mult(symbol: str, day: str) -> float:
        m = 1.0
        for ex, mult in split_events.get(symbol, ()):
            if ex > day:
                m *= mult
        return m

    basis: dict[str, list[tuple[str, float]]] = defaultdict(list)
    mismatched: set[str] = set()
    for day in trade_days:
        legs: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for t in by_day[day]:
            q = _num(t.get("quantity"))
            legs[t["symbol"]][0] += q * _num(t.get("price"))
            legs[t["symbol"]][1] += q
        for sym, (val, qty) in legs.items():
            close = price_on_or_before(sym, day) or price_on_or_after(sym, day)
            if not close or not qty:
                continue
            h = (val / qty) / (close * future_mult(sym, day))
            if 0.8 < h < 1.25:
                h = 1.0
            else:
                mismatched.add(sym)
            basis[sym].append((day, h))

    def basis_on(symbol: str, day: str) -> float:
        rows = basis.get(symbol)
        if not rows:
            return 1.0
        idx = bisect.bisect_right(rows, (day, float("inf"))) - 1
        return rows[idx][1] if idx >= 0 else 1.0

    # One snapshot per day the book changed: (open positions, cumulative realised, net cash).
    snapshots: list[tuple[list, float, float]] = []
    running: list[dict] = []
    net_cash = 0.0
    for day in trade_days:
        running.extend(by_day[day])
        for t in by_day[day]:
            gross = _num(t.get("price")) * _num(t.get("quantity"))
            charges = _num(t.get("charges"))
            if str(t.get("trade_type", "")).lower() == "buy":
                net_cash += gross + charges
            else:
                net_cash -= gross - charges
        positions, realized = compute_positions(running, actions=actions or [])
        opens = [(p.symbol, p.quantity, p.avg_cost, p.invested_value)
                 for p in positions if p.quantity > 0]
        snapshots.append((opens, realized, net_cash))

    days = sorted({d for d in calendar if d >= trade_days[0]} | set(trade_days))

    def _moved_before(c0: float | None, c1: float | None, p: float) -> float:
        """Share of the day's price move that had already happened by the time a trade
        executed at price `p` (0 = at the previous close, 1 = at today's close). Falls back
        to mid-day when the stock barely moved or a price is missing, where the ratio is
        meaningless."""
        if not c0 or not c1 or abs(c1 - c0) / c0 < 0.005:
            return 0.5
        return min(1.0, max(0.0, (p - c0) / (c1 - c0)))

    out: list[dict] = []
    prev_row: dict | None = None
    for day in days:
        idx = bisect.bisect_right(trade_days, day) - 1
        if idx < 0:
            continue
        opens, realized, net_in = snapshots[idx]

        market_value = invested = 0.0
        for symbol, qty, avg_cost, inv in opens:
            px = price_on_or_before(symbol, day)
            # No price history for this symbol (recent listing, delisted, renamed) — hold it
            # at cost rather than dropping it, so the curve doesn't step down for a data gap.
            market_value += qty * (px * basis_on(symbol, day) if px is not None else avg_cost)
            invested += inv

        # Capital genuinely at work today, for the time-weighted return. Yesterday's value
        # plus new money in proportion to how much of the day's move it was invested for,
        # minus sold shares for the part of the move they missed. Weighting by execution
        # price (which the tradebook records) means a tranche bought at the close adds
        # nothing to the base and one bought at the open adds all of it, so staged buying
        # and a lump sum give the same curve when the price path is the same.
        twr_base = None
        if prev_row is not None:
            twr_base = prev_row["market_value"]
            for t in by_day.get(day, []):
                sym, q, px_t = t["symbol"], _num(t.get("quantity")), _num(t.get("price"))
                # Closes in as-traded units, so they compare with the execution price.
                k = basis_on(sym, day) * future_mult(sym, day)
                c0 = price_on_or_before(sym, prev_row["date"])
                c1 = price_on_or_before(sym, day)
                c0, c1 = (c0 * k if c0 else c0), (c1 * k if c1 else c1)
                m = _moved_before(c0, c1, px_t)
                if str(t.get("trade_type", "")).lower() == "buy":
                    twr_base += q * px_t * (1.0 - m)
                else:
                    twr_base -= q * (c0 or px_t) * (1.0 - m)

        row = {
            "date": day,
            "invested_value": round(invested, 2),
            "realized_pnl": round(realized, 2),
            "net_invested": round(net_in, 2),
            "market_value": round(market_value, 2),
            "total_value": round(market_value + realized, 2),
            "pnl": round(market_value - net_in, 2),
            "twr_base": round(twr_base, 2) if twr_base is not None else None,
        }
        out.append(row)
        prev_row = row
    if out and mismatched:
        # Surfaced as a data-quality issue (R16/R17): usually a split or bonus missing from
        # the corporate-action feed, which also leaves the held quantity wrong.
        out[-1]["price_basis_symbols"] = sorted(mismatched)
    return out


def twr_series(rows: list[dict]) -> list[dict]:
    """Time-weighted return as a NAV indexed to 100 — the basis for every risk metric.

    Each day's return is the change in the value of what is HELD, with that day's cash
    flow removed:  r = (V_t - V_t-1 - flow_t) / V_t-1.  Buying more therefore doesn't
    register as a gain and selling doesn't register as a loss, which is the whole point:
    the previous series treated a full exit as a ~-90% day and then fed that into
    volatility, drawdown and beta.

    V is the market value of open positions only. Sale proceeds leave the portfolio as a
    negative flow on the same day, so they cancel out exactly rather than vanishing.

    This is the same NAV-unit method Zerodha Console uses for its performance curve, where
    deposits create units and withdrawals remove them so neither moves the NAV.
    """
    out: list[dict] = []
    nav = 100.0
    prev_value: float | None = None
    prev_net: float | None = None

    for row in rows:
        value = row["market_value"]
        net_in = row["net_invested"]
        if prev_value is not None:
            flow = net_in - prev_net
            # Money paid IN counts toward the day's capital base; money taken OUT does not.
            #
            # Contributions at start: a purchase is assumed to be working for the day, so it
            # belongs in the denominator. Dividing by the pre-flow value instead explodes
            # when a near-empty portfolio is topped up — on one real account, 434 rupees of
            # residual value followed by a 3,514 rupee purchase gave a -403% daily return,
            # drove NAV negative, and left 746 days of nonsense after it (max drawdown came
            # out at -1084%).
            #
            # Withdrawals at end: a sale is assumed to happen after the day's move, so the
            # base stays at yesterday's value and the day still earns on the money that was
            # invested. Putting withdrawals in the denominator would zero the base on a full
            # exit and silently discard that day's gain.
            gain = value - prev_value - flow
            # Prefer the execution-price-weighted base the series builder computed; rows
            # without one (a hand-built value/flow series) fall back to counting new money
            # in full and ignoring withdrawals.
            base = row.get("twr_base")
            if base is None:
                base = prev_value + max(flow, 0.0)
            # Below a rupee of base there is nothing to earn a return on — the day is pure
            # cash movement, so carry NAV flat rather than manufacturing a return from noise.
            if base > 1.0:
                r = gain / base
                # A long-only cash portfolio cannot lose more than everything in a day. If
                # this trips, the inputs disagree (a trade priced far from its close, or a
                # position that cannot be valued), and compounding it would corrupt every
                # later NAV. Hold flat instead of propagating a negative NAV.
                if r <= -1.0:
                    r = 0.0
            else:
                r = 0.0
            nav *= (1 + r)
            out.append({"date": row["date"], "nav": round(nav, 6), "ret": r})
        prev_value, prev_net = value, net_in
    return out


_BOOK_VALUE_KEYS = [
    "invested_value", "realized_pnl", "total_value", "market_value", "net_invested", "pnl",
    "nifty_50_value", "mid_cap_value", "large_cap_value", "small_cap_value",
    # The P&L lines are additive across clients (each is already value minus that client's
    # own deployed capital), so the book's line is just their sum.
    "nifty_50_pnl", "mid_cap_pnl", "large_cap_pnl", "small_cap_pnl",
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


def portfolio_xirr(trades: list[dict], dividends: list[dict] | None = None,
                   today: date | None = None) -> float | None:
    """Money-weighted return, suppressed under a year (R4) for the same reason CAGR is:
    annualising a few months turns a 5% gain into a headline 20%+."""
    if not trades:
        return None
    first = min(str(t["trade_date"])[:10] for t in trades)
    if ((today or date.today()) - date.fromisoformat(first)).days < 365:
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


def benchmark_series(trades: list[dict], prices: dict[str, float],
                     calendar: list[str] | None = None) -> list[dict]:
    """What the SAME cash flows would be worth in the index — the index-units method.

    Each buy purchases units of the index at that day's close; each sell redeems them. The
    result is directly comparable to the portfolio because both are valued with real prices
    on the same days. This is the Kaplan-Schoar public-market-equivalent construction.

    Emits `benchmark_pnl = benchmark_value - net_invested`, which is the number to plot.
    That baseline is what makes the comparison honest, and it is why the old chart was
    wrong: it subtracted OPEN COST BASIS from the benchmark. On a round trip where the
    index rose 10% alongside the portfolio, selling drove units to zero, so the benchmark
    line reported 0 gain against the portfolio's real +10% — the index appeared to do
    nothing whenever the client took a profit.

    Portfolio P&L reduces to `market_value - net_invested` (the realised and cost terms
    cancel), so subtracting the same `net_invested` here puts both on one baseline.

    Pass `calendar` to value the index on every trading day; without it the series only has
    points on trade days, which is what left the chart nearly empty.
    """
    import bisect

    if not trades:
        return []

    by_day: dict[str, list[dict]] = defaultdict(list)
    for t in trades:
        by_day[str(t["trade_date"])].append(t)
    trade_days = sorted(by_day)

    price_dates = sorted(prices)

    def price_on_or_before(day: str) -> float | None:
        idx = bisect.bisect_right(price_dates, day) - 1
        return prices[price_dates[idx]] if idx >= 0 else None

    # Units held and cash deployed after each day the book changed.
    units = net_cash = 0.0
    state: list[tuple[float, float]] = []
    for day in trade_days:
        px = price_on_or_before(day)
        for t in by_day[day]:
            gross = _num(t.get("price")) * _num(t.get("quantity"))
            charges = _num(t.get("charges"))
            if str(t.get("trade_type", "")).lower() == "buy":
                net_cash += gross + charges
                if px:
                    units += gross / px
            else:
                net_cash -= gross - charges
                if px:
                    units -= gross / px
        state.append((units, net_cash))

    days = sorted({d for d in (calendar or []) if d >= trade_days[0]} | set(trade_days))

    out: list[dict] = []
    for day in days:
        idx = bisect.bisect_right(trade_days, day) - 1
        if idx < 0:
            continue
        u, net_in = state[idx]
        px = price_on_or_before(day)
        value = u * px if px else 0.0
        out.append({
            "date": day,
            "benchmark_value": round(value, 2),
            "benchmark_pnl": round(value - net_in, 2),
        })
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

    `clients` = [{"id","name","trades":[...], optional "actions", "trade_count"}].

    Each client is valued exactly the way that client's own dashboard values it: its own
    corporate actions applied, each position priced on the exchange it was traded on, and
    unpriced positions left out of BOTH cost and market value. The book figures are then the
    sums of the client figures, so the manager page can never disagree with a client page.
    Previously the whole book was priced at once with one book-wide exchange map ("NSE if
    any client used NSE"), splits and bonuses were ignored, and an unpriced symbol dropped
    out of market value but stayed in cost. One BSE holding of VENUSREM was valued at the
    NSE price, overstating a Rs 2.5L account by Rs 4,979.
    """
    from collections import defaultdict

    # per-symbol aggregates across the whole book (priced positions only)
    invested_by_sym: dict[str, float] = defaultdict(float)
    market_by_sym: dict[str, float] = defaultdict(float)
    trade_count_by_sym: dict[str, int] = defaultdict(int)

    total_realized = 0.0
    total_invested = total_market = 0.0
    all_symbols: set[str] = set()
    # Book-wide "Invested" = the sum of each client's own peak capital at risk. Summed
    # per client rather than run over the merged trade stream, because one client's sell
    # must not offset another's buy — they are separate pools of money.
    book_peak_capital = 0.0
    by_client: list[dict] = []

    for c in clients:
        trades = c.get("trades", [])
        actions = c.get("actions") or []
        peak = peak_capital_deployed(matched_trades(trades, actions))
        book_peak_capital += peak
        for t in trades:
            trade_count_by_sym[t["symbol"]] += 1

        positions, realized = compute_positions(trades, actions)
        total_realized += realized
        opens = [p for p in positions if p.quantity > 0]
        quotes = get_quotes([p.symbol for p in opens], _exchange_map(trades)) if opens else {}

        cinv = cmv = 0.0
        for p in opens:
            all_symbols.add(p.symbol)
            ltp = quotes.get(p.symbol, {}).get("price")
            if ltp is None:
                continue        # unpriced: excluded from cost and value alike
            mv = ltp * p.quantity
            cmv += mv
            cinv += p.invested_value
            invested_by_sym[p.symbol] += p.invested_value
            market_by_sym[p.symbol] += mv
        total_invested += cinv
        total_market += cmv

        by_client.append({
            "id": c["id"], "name": c.get("name", ""),
            "client_code": c.get("client_code", ""),
            "status": c.get("status", "ACTIVE"),
            "trade_count": c.get("trade_count", len(trades)),
            "peak_capital": round(peak, 2),      # real investment: capital deployed
            "invested": round(cinv, 2),          # current investment: cost of what is held
            "market_value": round(cmv, 2),
            "unrealized_pnl": round(cmv - cinv, 2),
            "realized_pnl": round(realized, 2),
        })
    by_client.sort(key=lambda x: x["market_value"], reverse=True)
    total_unrealized = total_market - total_invested

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
            "invested_value": round(total_invested, 2),      # current investment (cost of holdings)
            "market_value": round(total_market, 2),
            "realized_pnl": round(total_realized, 2),
            "unrealized_pnl": round(total_unrealized, 2),
            "total_pnl": round(total_realized + total_unrealized, 2),
            # Denominator is peak capital at risk across the book, not open cost basis —
            # the latter inflates the number on any client with closed trades.
            "return_pct": round((total_realized + total_unrealized) / book_peak_capital * 100, 2)
            if book_peak_capital
            else 0.0,
            "peak_capital": round(book_peak_capital, 2),
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


def playbook_by_stock(trades: list[dict], min_days: int | None = None,
                      max_days: int | None = None) -> list[dict]:
    """Playbook rows collapsed to one row per stock — total qty, weighted-average
    buy/sell price, aggregate P&L. Weighted (not simple) averages, since round-trip
    lots vary in size and a simple average would misrepresent the actual entry/exit
    cost. Detail rows for a given symbol are fetched separately (existing
    GET /playbook?symbol=... already supports this) for the click-through modal.

    Optional min_days/max_days keep only round trips whose holding period falls in that
    inclusive range — intraday is 0..0, "within a week" is 1..7 — so the same by-stock
    view can be sliced by how long positions were actually held."""
    rows = compute_round_trips(trades)
    if min_days is not None:
        rows = [r for r in rows if (r.get("days") or 0) >= min_days]
    if max_days is not None:
        rows = [r for r in rows if (r.get("days") or 0) <= max_days]
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


def intraday_by_stock(records: list[dict]) -> list[dict]:
    """Same-day (intraday) round trips collapsed one row per stock, in the identical shape
    as playbook_by_stock. Input is engine.split_intraday's summary records
    ({symbol, date, quantity, buy_price, sell_price, pnl}) — all 0-day by definition, so
    they can't go through compute_round_trips (they aren't buy/sell rows)."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        groups[r["symbol"]].append(r)
    out = []
    for symbol, rs in groups.items():
        total_qty = sum(r["quantity"] for r in rs)
        total_buy_value = sum(r["buy_price"] * r["quantity"] for r in rs)
        total_sell_value = sum(r["sell_price"] * r["quantity"] for r in rs)
        total_pnl = sum(r["pnl"] for r in rs)
        out.append({
            "symbol": symbol,
            "trades_count": len(rs),
            "total_qty": round(total_qty, 4),
            "avg_buy_price": round(total_buy_value / total_qty, 2) if total_qty else 0,
            "avg_sell_price": round(total_sell_value / total_qty, 2) if total_qty else 0,
            "total_pnl": round(total_pnl, 2),
            "pnl_pct": round(total_pnl / total_buy_value * 100, 2) if total_buy_value else 0,
            "avg_days": 0,
        })
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

def _returns_of(series: list[dict]) -> list[tuple[str, float]]:
    """(date, daily return) pairs from a series, preferring the TWR nav when present.

    Accepts either a nav series from twr_series() or a raw value series, so callers can
    pass a benchmark's price history through the same path.
    """
    out: list[tuple[str, float]] = []
    if not series:
        return out
    if "ret" in series[0]:
        return [(r["date"], r["ret"]) for r in series]
    prev = None
    for row in series:
        v = row.get("nav", row.get("total_value"))
        if v is not None and prev is not None and prev > 0:
            out.append((row["date"], (v - prev) / prev))
        if v is not None:
            prev = v
    return out


def calculate_daily_returns(performance_series: list[dict]) -> list[float]:
    """Daily returns as plain floats. Prefer _returns_of when dates are needed."""
    return [r for _, r in _returns_of(performance_series)]


def calculate_cagr(nav_series: list[dict]) -> float | None:
    """Annualised time-weighted return, from the NAV curve.

    Taking it from the NAV means deposits and withdrawals don't count as performance. The
    previous version divided total P&L by the LAST row's open cost basis, so a book that
    had closed most of its positions showed an enormous return (a 50k gain on a 10k
    remaining position read as 500%).

    Returns None for periods under a year rather than extrapolating. GIPS forbids
    annualising a partial year because it invents a return the assets never earned, and
    Zerodha Console suppresses its own XIRR for the same reason.
    """
    if not nav_series or len(nav_series) < 2:
        return None

    start_nav = nav_series[0].get("nav")
    end_nav = nav_series[-1].get("nav")
    if not start_nav or end_nav is None or start_nav <= 0:
        return None

    start = datetime.strptime(nav_series[0]["date"], "%Y-%m-%d").date()
    end = datetime.strptime(nav_series[-1]["date"], "%Y-%m-%d").date()
    days = (end - start).days
    if days < 365:
        return None

    years = days / 365.25
    growth = end_nav / start_nav
    if growth <= 0:
        return None
    return growth ** (1 / years) - 1


def calculate_total_return(nav_series: list[dict]) -> float | None:
    """Cumulative time-weighted return over the whole period, not annualised.

    This is what to show when the period is under a year and CAGR is withheld.
    """
    if not nav_series or len(nav_series) < 2:
        return None
    start_nav = nav_series[0].get("nav")
    end_nav = nav_series[-1].get("nav")
    if not start_nav or end_nav is None or start_nav <= 0:
        return None
    return end_nav / start_nav - 1


def calculate_volatility(nav_series: list[dict]) -> float | None:
    """Annualised standard deviation of daily time-weighted returns.

    Meaningful only now that the series has a point per trading day: annualising by
    sqrt(252) assumes the observations ARE consecutive trading days, which was false when
    the series only had a row per trade (gaps of up to 48 days between "daily" returns).
    """
    returns = calculate_daily_returns(nav_series)
    if len(returns) < 2:
        return None
    import statistics
    return statistics.stdev(returns) * (252 ** 0.5)


def calculate_max_drawdown(nav_series: list[dict]) -> float | None:
    """Worst peak-to-trough fall of the NAV, as a negative decimal."""
    if not nav_series:
        return None
    peak = float("-inf")
    worst = 0.0
    for row in nav_series:
        v = row.get("nav")
        if v is None:
            continue
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, (v - peak) / peak)
    return worst if worst < 0 else None


def calculate_current_drawdown(nav_series: list[dict]) -> float | None:
    """How far below its all-time peak the NAV sits today, as a negative decimal."""
    if not nav_series:
        return None
    navs = [r["nav"] for r in nav_series if r.get("nav") is not None]
    if not navs:
        return None
    peak = max(navs)
    return (navs[-1] - peak) / peak if peak > 0 else None


def calculate_sharpe_ratio(nav_series: list[dict], risk_free_rate: float = RISK_FREE_RATE) -> float | None:
    """Sharpe from daily excess returns: mean(r - rf_daily) / stdev(r) * sqrt(252).

    Built from the daily series rather than from (CAGR - rf) / volatility, which mixes a
    geometric numerator with an arithmetic denominator and needs a full year of history
    before CAGR exists at all. This version works on any period of a few weeks or more.

    There used to be TWO functions with this name in this module; the second silently
    shadowed the first, expected raw trades, and looked for an "action" key our trades
    don't have — so it returned None for every portfolio and the Sharpe card was always
    blank. There is now exactly one.
    """
    returns = calculate_daily_returns(nav_series)
    if len(returns) < 2:
        return None
    import statistics
    sd = statistics.stdev(returns)
    if sd == 0:
        return None
    daily_rf = risk_free_rate / 252
    mean_excess = statistics.mean(returns) - daily_rf
    return mean_excess / sd * (252 ** 0.5)


def calculate_benchmark_cagr(benchmark_nav: list[dict]) -> float | None:
    return calculate_cagr(benchmark_nav)


def calculate_beta(portfolio_returns, benchmark_returns) -> float | None:
    """Beta = cov(portfolio, benchmark) / var(benchmark).

    Both arguments may be (date, return) pairs, in which case they are matched BY DATE.
    The old version aligned two plain lists by trailing position after each had already
    dropped its own missing days, so the pairs could be silently offset — comparing the
    portfolio's Tuesday against the index's Thursday and reporting the result as beta.
    """
    def _as_map(seq):
        if seq and isinstance(seq[0], tuple):
            return dict(seq)
        return None

    pm, bm = _as_map(portfolio_returns), _as_map(benchmark_returns)
    if pm is not None and bm is not None:
        shared = sorted(set(pm) & set(bm))
        port = [pm[d] for d in shared]
        bench = [bm[d] for d in shared]
    else:
        port = [r for _, r in portfolio_returns] if (portfolio_returns and isinstance(portfolio_returns[0], tuple)) else list(portfolio_returns)
        bench = [r for _, r in benchmark_returns] if (benchmark_returns and isinstance(benchmark_returns[0], tuple)) else list(benchmark_returns)
        n = min(len(port), len(bench))
        port, bench = port[-n:], bench[-n:]

    if len(port) < 2 or len(bench) < 2:
        return None

    import statistics
    bench_mean = statistics.mean(bench)
    port_mean = statistics.mean(port)
    cov = sum((p - port_mean) * (b - bench_mean) for p, b in zip(port, bench)) / len(port)
    var = sum((b - bench_mean) ** 2 for b in bench) / len(bench)
    return cov / var if var else None


def calculate_alpha(portfolio_return: float | None, benchmark_return: float | None,
                    beta: float | None, risk_free_rate: float = RISK_FREE_RATE) -> float | None:
    """Jensen's alpha: actual return minus the return beta alone would predict."""
    if portfolio_return is None or benchmark_return is None or beta is None:
        return None
    expected = risk_free_rate + beta * (benchmark_return - risk_free_rate)
    return portfolio_return - expected


def compute_performance_metrics(nav_series: list[dict],
                                benchmark_nav: list[dict] | None = None,
                                risk_free_rate: float = RISK_FREE_RATE) -> dict:
    """Every Phase 1 metric, all derived from the time-weighted NAV curve.

    `nav_series` comes from twr_series(); `benchmark_nav` is the same transform applied to
    the index's own price history, so portfolio and benchmark are measured identically.
    """
    if not nav_series:
        return {}

    cagr = calculate_cagr(nav_series)
    total_return = calculate_total_return(nav_series)
    volatility = calculate_volatility(nav_series)
    sharpe = calculate_sharpe_ratio(nav_series, risk_free_rate)
    max_dd = calculate_max_drawdown(nav_series)
    current_dd = calculate_current_drawdown(nav_series)

    beta = alpha = benchmark_cagr = benchmark_total_return = None
    if benchmark_nav and len(benchmark_nav) >= 2:
        benchmark_cagr = calculate_benchmark_cagr(benchmark_nav)
        benchmark_total_return = calculate_total_return(benchmark_nav)
        beta = calculate_beta(_returns_of(nav_series), _returns_of(benchmark_nav))
        # Compare like with like: annualised against annualised when a full year exists,
        # otherwise cumulative against cumulative.
        port_r, bench_r = (cagr, benchmark_cagr) if cagr is not None else (total_return, benchmark_total_return)
        alpha = calculate_alpha(port_r, bench_r, beta, risk_free_rate)

    start = datetime.strptime(nav_series[0]["date"], "%Y-%m-%d").date()
    end = datetime.strptime(nav_series[-1]["date"], "%Y-%m-%d").date()

    return {
        "cagr": round(cagr, 4) if cagr is not None else None,
        "total_return": round(total_return, 4) if total_return is not None else None,
        "volatility": round(volatility, 4) if volatility is not None else None,
        "sharpe_ratio": round(sharpe, 4) if sharpe is not None else None,
        "max_drawdown": round(max_dd, 4) if max_dd is not None else None,
        "current_drawdown": round(current_dd, 4) if current_dd is not None else None,
        "beta": round(beta, 4) if beta is not None else None,
        "alpha": round(alpha, 4) if alpha is not None else None,
        "benchmark_cagr": round(benchmark_cagr, 4) if benchmark_cagr is not None else None,
        "benchmark_total_return": round(benchmark_total_return, 4) if benchmark_total_return is not None else None,
        "days_held": (end - start).days,
        "observations": len(nav_series),
        "start_date": str(start),
        "end_date": str(end),
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
            _sector_of[sym] = classify(sym, network=False).get("sector", "Unclassified")
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


def compute_risk_monitoring(nav_series: list[dict], trades: list[dict],
                            holdings: list[dict] | None = None) -> dict:
    """Phase 4: Risk monitoring (concentration, health score, alerts).

    `nav_series` is the time-weighted NAV from twr_series(), so volatility and drawdown
    here mean the same thing they do on the metrics cards.
    """
    from app.services.engine import compute_positions
    from app.services.securities import classify

    if not nav_series:
        return {"error": "No data"}

    # Weight positions by MARKET value when priced holdings are supplied, the same basis the
    # Concentration panel uses. Weighting by cost here gave two different "Largest sector"
    # figures on one page (40.9% against 39.0%). Unpriced holdings and the no-holdings
    # fallback use cost basis so nothing silently drops out.
    rows: list[tuple[str, float, str, str]] = []   # (symbol, weight value, sector, cap)
    if holdings:
        for h in holdings:
            v = h.get("market_value")
            if v is None:
                v = h.get("invested_value") or 0.0
            rows.append((h["symbol"], float(v), h.get("sector") or "Unclassified", h.get("cap") or "Unknown"))
    else:
        positions, _ = compute_positions(trades)
        for p in positions:
            if p.quantity > 0:
                meta = classify(p.symbol)
                rows.append((p.symbol, float(p.invested_value or 0.0),
                             meta.get("sector", "Unclassified"), meta.get("cap", "Unknown")))

    rows = [r for r in rows if r[1] > 0]
    if not rows:
        return {"error": "No open positions"}

    total_inv = sum(r[1] for r in rows)

    # Top 10 concentration
    top_10_pct = round(sum(r[1] for r in sorted(rows, key=lambda r: r[1], reverse=True)[:10]) / total_inv * 100, 1)

    # Sector concentration
    by_sector = defaultdict(float)
    by_cap = defaultdict(float)
    for _sym, v, sector, cap in rows:
        by_sector[sector] += v
        by_cap[cap] += v

    sector_pcts = {s: round(v / total_inv * 100, 1) for s, v in by_sector.items()}
    largest_sector = max(sector_pcts.items(), key=lambda x: x[1])[0] if sector_pcts else None
    largest_sector_pct = max(sector_pcts.values()) if sector_pcts else 0
    cap_pcts = {c: round(v / total_inv * 100, 1) for c, v in by_cap.items()}

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

    # These three are DECIMALS (0.25 == 25%), but were compared against 25, -30 and -15 as
    # though they were percentages — so no volatility or drawdown penalty could ever fire
    # and every portfolio scored at least 85 with an empty alert list.
    volatility = calculate_volatility(nav_series) or 0.0
    if volatility > 0.25:
        score -= 10
    elif volatility > 0.20:
        score -= 5

    max_dd = calculate_max_drawdown(nav_series) or 0.0
    if max_dd < -0.30:
        score -= 15
    elif max_dd < -0.20:
        score -= 10

    current_dd = calculate_current_drawdown(nav_series) or 0.0
    if current_dd < -0.15:
        score -= 10
    elif current_dd < -0.10:
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
        "total_positions": len(rows),
        "alerts": [a for a in [
            "High concentration" if top_10_pct > 70 else None,
            "Sector overweight" if largest_sector_pct > 40 else None,
            "High volatility" if volatility > 0.25 else None,
            "Deep drawdown" if max_dd < -0.30 else None,
        ] if a is not None]
    }
