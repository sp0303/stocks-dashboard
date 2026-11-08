"""Pure compute for the portfolio worker: DB rows in, portfolio.* records out.

No I/O and no clock (``today`` is a parameter). All metric math is pi_core's
(FIFOEngine, TWR, capital, returns, risk, drawdown, XIRR) -- this module only
adapts rows to pi_core models and pi_core results to table rows. This is the
same pipeline the worker and ``libs/pi_core/scripts/seed_v2_data.py`` used.
"""

from __future__ import annotations

import json
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pi_core.engine.fifo import EngineResult, FIFOEngine
from pi_core.engine.matching import match_trades_fifo
from pi_core.engine.segments import separate_segments
from pi_core.metrics.capital import calculate_capital_metrics
from pi_core.metrics.drawdown import calculate_drawdown_series
from pi_core.metrics.returns import calculate_returns
from pi_core.metrics.risk import calculate_risk_metrics
from pi_core.metrics.xirr import calculate_xirr
from pi_core.models import ActionType, CorporateAction, Segment, Side, Trade
from pi_core.pricing import MAX_PRICE_CARRY_DAYS
from pi_core.series.book import book_metrics
from pi_core.series.calendar import generate_trading_calendar
from pi_core.series.twr import calculate_twr_series

ENGINE_VERSION = "v2.3"  # v2.3: ADR-0009 other-exchange price fallback; v2.2: R6 unpriced exclusion, R9 pools, per-key TWR
MAX_STORED_WARNINGS = 50

PriceLookup = Callable[[str, str, date], float | None]


def trades_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[Trade]:
    out = []
    for r in rows:
        extra = r.get("extra")
        out.append(
            Trade(
                trade_id=str(r["trade_id"]),
                trade_date=r["trade_date"],
                symbol=r["symbol"],
                exchange=r["exchange"],
                side=Side.BUY if r["trade_type"] == "buy" else Side.SELL,
                quantity=float(r["quantity"]),
                price=float(r["price"]),
                charges=None
                if r.get("charges") is None
                else float(r["charges"]),  # R15
                segment=Segment.DERIVATIVE
                if r.get("segment") == "FO"
                else Segment.EQUITY,
                extra=json.loads(extra) if isinstance(extra, str) else (extra or {}),
            )
        )
    return out


def actions_from_rows(rows: Iterable[Mapping[str, Any]]) -> list[CorporateAction]:
    out = []
    for r in rows:
        try:
            act = ActionType(r["type"])
        except ValueError:
            act = ActionType.OTHER
        mult = r.get("qty_multiplier")
        out.append(
            CorporateAction(
                r["symbol"], act, r["ex_date"], 1.0, float(mult) if mult else 1.0
            )
        )
    return out


def build_price_lookup(
    rows: Iterable[tuple[str, str, date, float]],
    max_carry_days: int = MAX_PRICE_CARRY_DAYS,
) -> PriceLookup:
    """Close lookup with bounded carry-forward (R6, ADR-0009).

    A lot is valued at the close of its own exchange; with none usable, at the same
    symbol's close on the other exchange (a BSE-bought lot of a stock that trades on the NSE
    is the same share). Exchanges are never averaged or merged: it is one close, from one
    place. ``lookup.own`` is the strict own-exchange lookup, so callers can flag the fallback.
    A holiday or a suspended day uses the last close within ``max_carry_days``.
    """
    series: dict[tuple[str, str], tuple[list[date], list[float]]] = {}
    for sym, exch, d, close in sorted(rows, key=lambda x: (x[0], x[1], x[2])):
        dates, closes = series.setdefault((sym, exch), ([], []))
        dates.append(d)
        closes.append(float(close))

    def own(sym: str, exch: str, d: date) -> float | None:
        s = series.get((sym, exch))
        if not s:
            return None
        i = bisect_right(s[0], d) - 1
        if i < 0 or (d - s[0][i]).days > max_carry_days:
            return None
        return s[1][i]

    def lookup(sym: str, exch: str, d: date) -> float | None:
        px = own(sym, exch, d)
        if px is not None:
            return px
        for other in ("NSE", "BSE"):
            if other != exch:
                px = own(sym, other, d)
                if px is not None:
                    return px
        return None

    lookup.own = own  # type: ignore[attr-defined]
    return lookup


def _priced_on_other_exchange(
    positions: list, price_lookup: PriceLookup, today: date
) -> list[dict[str, str]]:
    """Open lots valued at the other exchange's close (shown, never silent)."""
    own = getattr(price_lookup, "own", None)
    if own is None:
        return []
    out = []
    for p in positions:
        sym, exch = p[0], p[1]
        if sym is None or own(sym, exch, today) is not None or price_lookup(sym, exch, today) is None:
            continue
        other = "NSE" if exch == "BSE" else "BSE"
        out.append({"symbol": sym, "exchange": exch, "priced_on": other})
    return out


def engine_calendar(first: date, today: date, closed_days: set[date]) -> list[date]:
    """Weekdays minus known closed days (market.trading_calendar is_open = false), R11."""
    return generate_trading_calendar(first, today, known_holidays=closed_days)


@dataclass
class ClientResult:
    overview: dict[str, Any]
    metrics: dict[str, Any]
    obs: int
    daily: list[tuple] = field(
        default_factory=list
    )  # client_daily rows minus client_id
    positions: list[tuple[str, str, float, float, float, date]] = field(
        default_factory=list
    )
    warnings: list[str] = field(default_factory=list)


def _daily_rows(result: EngineResult, nav_series) -> list[tuple]:
    nav_by_date = {p.point_date: p for p in nav_series}
    rows, net_invested = [], 0.0
    for s in result.snapshots:
        net_invested += s.net_cash_flow
        p = nav_by_date.get(s.snapshot_date)
        if p is None:
            continue
        rows.append(
            (
                s.snapshot_date,
                round(s.market_value, 2),
                round(s.open_cost, 2),
                round(net_invested, 2),
                round(s.realized_pnl_cumulative, 2),
                round(p.capital_base, 2),
                p.daily_return,
                p.nav,
                round(s.unpriced_cost, 2),
            )
        )
    return rows


def _positions(
    result: EngineResult,
) -> list[tuple[str, str, float, float, float, date]]:
    """Every open (symbol, exchange) holding, priced or not (R6 shows unpriced ones)."""
    out = []
    for (sym, exch), lots in sorted(result.open_lots.items()):
        qty = sum(l.quantity for l in lots)
        cost = sum(l.total_cost for l in lots)
        if qty <= 1e-6:
            continue
        out.append(
            (sym, exch, qty, cost / qty, round(cost, 2), min(l.buy_date for l in lots))
        )
    return out


def _unpriced(result: EngineResult) -> list[dict[str, Any]]:
    """R6.4: holdings with no usable price on the last day, excluded from cost and value."""
    last = result.latest_snapshot
    if last is None:
        return []
    return [
        {
            "symbol": sym,
            "exchange": exch,
            "quantity": last.marks[(sym, exch)].quantity,
            "cost": round(last.marks[(sym, exch)].cost, 2),
        }
        for sym, exch in last.unpriced
    ]


def _pool_pnl(trades: list[Trade]) -> dict[str, Any]:
    """R9: intraday / derivatives report P&L and count only; never capital."""
    matched, _, _ = match_trades_fifo(trades)
    return {
        "trades": len(trades),
        "pnl": round(sum(m.realized_pnl for m in matched), 2),
    }


def compute_client(
    trades: list[Trade],
    actions: list[CorporateAction],
    price_lookup: PriceLookup,
    today: date,
    closed_days: set[date],
) -> ClientResult:
    """Runs the pi_core pipeline on the delivery pool (R9).

    Same-day round trips and F&O are split out first: their cash is not invested
    capital, and leaving them in booked intraday profit as NAV return on whatever small
    delivery base was held that day (the +251 % on a Rs 903 base).
    """
    calendar = engine_calendar(min(t.trade_date for t in trades), today, closed_days)
    delivery, intraday, derivatives = separate_segments(trades)
    result = FIFOEngine(delivery, actions, price_lookup=price_lookup).run(
        calendar, as_of=today
    )
    nav_series, twr_warn = calculate_twr_series(
        result.snapshots, delivery, close_price_lookup=price_lookup
    )
    cap = calculate_capital_metrics(result.snapshots)
    flows = [
        (s.snapshot_date, -s.net_cash_flow)
        for s in result.snapshots
        if abs(s.net_cash_flow) > 1e-4
    ]
    xirr = calculate_xirr(
        flows, terminal_value=cap.market_value if cap else 0.0, as_of=today
    )
    unpriced = _unpriced(result)
    positions = _positions(result)
    via_other = _priced_on_other_exchange(positions, price_lookup, today)
    warnings = (
        list(result.warnings)
        + list(twr_warn)
        + [
            f"No usable price for {u['symbol']} ({u['exchange']}): excluded from "
            "market value and current invested (R6)."
            for u in unpriced
        ]
        + [
            f"{v['symbol']} ({v['exchange']}) has no {v['exchange']} close: valued at its "
            f"{v['priced_on']} close (ADR-0009)."
            for v in via_other
        ]
    )
    overview = _overview(
        cap, calculate_returns(nav_series), result, unpriced, positions
    )
    overview["priced_on_other_exchange"] = via_other
    overview["intraday"] = _pool_pnl(intraday)
    overview["derivatives"] = _pool_pnl(derivatives)
    overview["warnings"] = warnings[:MAX_STORED_WARNINGS]
    return ClientResult(
        overview,
        _metrics(nav_series, xirr),
        len(nav_series),
        _daily_rows(result, nav_series),
        positions,
        warnings,
    )


def _overview(cap, ret, result: EngineResult, unpriced, positions) -> dict[str, Any]:
    return {
        "market_value": cap.market_value if cap else 0.0,
        "capital_deployed": cap.capital_deployed if cap else 0.0,
        "current_invested": cap.current_invested if cap else 0.0,
        "realized_pnl": cap.realized_pnl if cap else 0.0,
        "unrealized_pnl": cap.unrealized_pnl if cap else 0.0,
        "total_pnl": cap.total_pnl if cap else 0.0,
        "return_on_capital": cap.return_on_capital if cap else 0.0,
        "cagr": ret.cagr if ret else None,
        "unmatched_sells": len(result.unmatched_sells),
        # R6.4: listed, and outside current_invested / market_value / unrealized_pnl
        "unpriced": unpriced,
        "unpriced_cost": round(sum(u["cost"] for u in unpriced), 2),
        "open_positions": len(positions),  # priced + unpriced, as the holdings table
        "priced_positions": len(positions) - len(unpriced),
    }


def _metrics(nav_series, xirr) -> dict[str, Any]:
    ret = calculate_returns(nav_series)
    risk = calculate_risk_metrics(nav_series)
    dd = calculate_drawdown_series(nav_series)
    return {
        "total_return": ret.total_return if ret else 0.0,
        "cagr": ret.cagr if ret else None,
        "annualized_volatility": risk.annualized_volatility if risk else None,
        "sharpe_ratio": risk.sharpe_ratio if risk else None,
        "max_drawdown": dd.max_drawdown if dd else None,
        "current_drawdown": dd.current_drawdown if dd else None,
        "beta": risk.beta if risk else None,
        "alpha": risk.alpha if risk else None,
        "xirr": xirr,
    }


def compute_manager_metrics(
    client_daily: Iterable[tuple[date, float | None, float | None, float]],
) -> dict[str, Any]:
    """Book series metrics from client_daily (as_of, day_return, twr_base, market_value).

    R5: the same pi_core function the API uses; for the worker to precompute.
    """
    return book_metrics(client_daily)
