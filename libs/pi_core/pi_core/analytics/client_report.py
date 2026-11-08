"""Assembles the per-client analytics payload (precomputed by the portfolio worker, HLD D1).

Inputs are plain pi_core models + already-loaded reference data; output is a
JSON-ready dict. Pools are kept apart (R9): delivery feeds allocation, playbook
and trade analytics; intraday is reported on its own; derivatives are counted only
(notional is never capital). Matched shares only (R7). ``today`` is a parameter.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from pi_core.analytics.allocation import calculate_symbol_allocation
from pi_core.analytics.benchmark_compare import (
    benchmark_track,
    beta_alpha,
    nav_points,
    portfolio_returns,
)
from pi_core.analytics.closed_trades import ClosedTrade, closed_trades_from_matches
from pi_core.analytics.exposure import (
    HoldingValue,
    SecurityClass,
    allocation_matrix,
    concentration_summary,
    unpriced,
)
from pi_core.analytics.health import health_score
from pi_core.analytics.highlights import holding_highlights
from pi_core.analytics.playbook import playbook_by_stock
from pi_core.analytics.trade_analytics import pool_summary, trade_analytics
from pi_core.engine.fifo import FIFOEngine
from pi_core.engine.matching import match_trades_fifo
from pi_core.engine.segments import separate_segments
from pi_core.metrics.drawdown import calculate_drawdown_series
from pi_core.metrics.risk import calculate_risk_metrics
from pi_core.models import CorporateAction, NAVPoint, Trade

PAYLOAD_VERSION = 1
BETA_BENCHMARK = "^NSEI"  # Nifty 50
Key = tuple[str, str]
PriceLookup = Callable[[str, str, date], float | None]


@dataclass(frozen=True)
class DailyRow:
    """One portfolio.client_daily row (the R11 trading-calendar series)."""

    as_of: date
    market_value: float
    net_invested: float
    nav: float
    day_return: float | None
    unpriced_cost: float = 0.0  # held but unpriced: out of market_value, valued at cost here


@dataclass(frozen=True)
class BenchmarkInput:
    code: str
    label: str
    is_tri: bool
    levels: Mapping[date, float] = field(default_factory=dict)


@dataclass(frozen=True)
class ReportInputs:
    trades: Sequence[Trade]
    actions: Sequence[CorporateAction]
    calendar: Sequence[date]
    price_lookup: PriceLookup
    today: date
    classes: Mapping[Key, SecurityClass]
    notes: Mapping[str, str]
    manual_trades: Sequence[Mapping[str, Any]]
    daily: Sequence[DailyRow]
    benchmarks: Sequence[BenchmarkInput]


@dataclass
class _Pools:
    delivery: list[ClosedTrade]
    intraday: list[ClosedTrade]
    holdings: list[HoldingValue]
    entry_dates: dict[Key, date]
    closed_peaks: dict[Key, float]
    derivative_trades: int
    unmatched_sells: int


def _holdings(open_lots: Mapping[Key, Sequence[Any]], lookup: PriceLookup, today: date):
    holdings, entries = [], {}
    for (sym, exch), lots in sorted(open_lots.items()):
        qty = sum(l.quantity for l in lots)
        if qty <= 1e-6:
            continue
        cost = sum(l.total_cost for l in lots)
        px = lookup(sym, exch, today)
        holdings.append(HoldingValue(sym, exch, qty, cost, qty * px if px is not None else None))
        entries[(sym, exch)] = min(l.buy_date for l in lots)
    return holdings, entries


def _pools(inp: ReportInputs) -> _Pools:
    delivery, intraday, derivs = separate_segments(list(inp.trades))
    res = FIFOEngine(delivery, list(inp.actions), price_lookup=inp.price_lookup).run(
        list(inp.calendar), as_of=inp.today
    )
    intra_matched, _, _ = match_trades_fifo(intraday)
    holdings, entries = _holdings(res.open_lots, inp.price_lookup, inp.today)
    open_keys = {(h.symbol, h.exchange) for h in holdings}
    peaks = {
        (a.symbol, a.exchange): a.peak_capital
        for a in calculate_symbol_allocation(delivery, 1.0)
        if (a.symbol, a.exchange) not in open_keys
    }
    return _Pools(
        delivery=closed_trades_from_matches(res.matched_trades),
        intraday=closed_trades_from_matches(intra_matched),
        holdings=holdings,
        entry_dates=entries,
        closed_peaks=peaks,
        derivative_trades=len(derivs),
        unmatched_sells=len(res.unmatched_sells),
    )


def _nav(daily: Sequence[DailyRow]) -> list[NAVPoint]:
    return nav_points(
        [r.as_of for r in daily], [r.nav for r in daily], [r.day_return for r in daily]
    )


def _health(conc: Mapping[str, Any], nav: list[NAVPoint]) -> dict[str, Any] | None:
    if not conc["holdings_count"]:
        return None
    risk = calculate_risk_metrics(nav)
    dd = calculate_drawdown_series(nav) if nav else None
    sector = conc["largest_sector"]
    return health_score(
        {
            "top10_weight": conc["top10_weight"],
            "largest_sector_weight": sector["weight"] if sector else None,
            "volatility": risk.annualized_volatility,
            "max_drawdown": dd.max_drawdown if dd else None,
            "current_drawdown": dd.current_drawdown if dd else None,
        }
    )


def _performance(daily: Sequence[DailyRow], nav, benches: Sequence[BenchmarkInput]) -> dict:
    days = [r.as_of for r in daily]
    ni = [r.net_invested for r in daily]
    out = {
        "dates": [d.isoformat() for d in days],
        "net_invested": ni,
        "market_value": [r.market_value for r in daily],
        # R6: unpriced holdings leave value AND cost, so they must not show up as a loss here
        "portfolio_pnl": [r.market_value + r.unpriced_cost - r.net_invested for r in daily],
        **portfolio_returns(nav),
        "benchmarks": [],
    }
    for b in benches:
        track = benchmark_track(days, ni, b.levels)
        out["benchmarks"].append({"code": b.code, "label": b.label, "is_tri": b.is_tri, **track})
    return out


def _summary(inp: ReportInputs, p: _Pools, nav: list[NAVPoint]) -> dict[str, Any]:
    conc = concentration_summary(p.holdings, inp.classes)
    nifty = next((b for b in inp.benchmarks if b.code == BETA_BENCHMARK), None)
    return {
        "allocation": allocation_matrix(p.holdings, p.closed_peaks, inp.classes),
        "unpriced": unpriced(p.holdings),
        "concentration": conc,
        "health": _health(conc, nav),
        "beta_benchmark": nifty.label if nifty else None,
        **beta_alpha(nav, nifty.levels if nifty else {}),
        "intraday": pool_summary(p.intraday),
        "derivative_trades": p.derivative_trades,
        "unmatched_sells": p.unmatched_sells,
        "highlights": holding_highlights(p.holdings, p.entry_dates, p.delivery, inp.today),
        "manual_trades": list(inp.manual_trades),
    }


def build_client_report(inp: ReportInputs) -> dict[str, Any]:
    """The whole payload; sections are read independently by the API."""
    p = _pools(inp)
    nav = _nav(inp.daily)
    return {
        "version": PAYLOAD_VERSION,
        "as_of": inp.today.isoformat(),
        "summary": _summary(inp, p, nav),
        "trades": {"delivery": trade_analytics(p.delivery), "intraday": trade_analytics(p.intraday)},
        "playbook": {
            "delivery": playbook_by_stock(p.delivery, inp.notes, "delivery"),
            "intraday": playbook_by_stock(p.intraday, inp.notes, "intraday"),
        },
        "performance": _performance(inp.daily, nav, inp.benchmarks),
    }


def closed_round_trips(inp: ReportInputs) -> list[dict[str, Any]]:
    """Delivery closed trades as ``portfolio.round_trips`` rows (matched shares only, R7).

    The manager-book "Closed trades" tab reads these. Fills of one symbol that share a buy
    date and a sell date are merged into one round trip (quantity and P&L summed, prices
    quantity-weighted): the table's key is (client, symbol, buy_date, sell_date, quantity),
    so unmerged partial fills of equal size would collide."""
    merged: dict[tuple[str, date, date], dict[str, Any]] = {}
    for t in _pools(inp).delivery:
        m = merged.setdefault(
            (t.symbol, t.first_buy_date, t.sell_date),
            {"quantity": 0.0, "buy_value": 0.0, "sell_value": 0.0, "pnl": 0.0, "day_qty": 0.0},
        )
        m["quantity"] += t.quantity
        m["buy_value"] += t.buy_value
        m["sell_value"] += t.sell_value
        m["pnl"] += t.pnl
        m["day_qty"] += t.holding_days * t.quantity
    return [
        {
            "symbol": sym,
            "buy_date": buy,
            "sell_date": sell,
            "quantity": m["quantity"],
            "buy_price": m["buy_value"] / m["quantity"],
            "sell_price": m["sell_value"] / m["quantity"],
            "pnl": m["pnl"],
            "days": round(m["day_qty"] / m["quantity"]),
        }
        for (sym, buy, sell), m in merged.items()
        if m["quantity"] > 0
    ]
