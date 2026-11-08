"""Trade analytics over closed trades of ONE pool (R9): delivery or intraday, never mixed.

Ratios are decimals (R12). Profit factor is None when there are no losses (no
infinity in JSON). Pure: no I/O, no clock.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from typing import Any

from pi_core.analytics.closed_trades import ClosedTrade

# Return-on-cost buckets, decimals (R12): lower bound inclusive, upper exclusive.
_INF = float("inf")
DISTRIBUTION_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("< -20%", -_INF, -0.20),
    ("-20% to -10%", -0.20, -0.10),
    ("-10% to -5%", -0.10, -0.05),
    ("-5% to 0%", -0.05, 0.0),
    ("0% to 5%", 0.0, 0.05),
    ("5% to 10%", 0.05, 0.10),
    ("10% to 20%", 0.10, 0.20),
    ("20% to 50%", 0.20, 0.50),
    ("> 50%", 0.50, _INF),
)
# Holding-period buckets in whole days, inclusive.
HOLDING_BUCKETS: tuple[tuple[str, int, int | None], ...] = (
    ("Same day", 0, 0),
    ("1-7 days", 1, 7),
    ("8-30 days", 8, 30),
    ("31-90 days", 31, 90),
    ("91-365 days", 91, 365),
    ("Over 1 year", 366, None),
)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _group_stats(trades: Sequence[ClosedTrade]) -> dict[str, Any]:
    n = len(trades)
    wins = sum(1 for t in trades if t.is_win)
    return {
        "trades": n,
        "wins": wins,
        "pnl": sum(t.pnl for t in trades),
        "win_rate": wins / n if n else None,
    }


def _bucketed(
    trades: Sequence[ClosedTrade], key: Callable[[ClosedTrade], str], order: Sequence[str]
) -> list[dict[str, Any]]:
    groups: dict[str, list[ClosedTrade]] = defaultdict(list)
    for t in trades:
        groups[key(t)].append(t)
    return [{"bucket": k, **_group_stats(groups[k])} for k in order if groups.get(k)]


def _distribution_key(t: ClosedTrade) -> str:
    r = t.pnl_pct if t.pnl_pct is not None else 0.0
    for label, lo, hi in DISTRIBUTION_BUCKETS:
        if lo <= r < hi:
            return label
    return DISTRIBUTION_BUCKETS[-1][0]


def _holding_key(t: ClosedTrade) -> str:
    d = round(t.holding_days)
    for label, lo, hi in HOLDING_BUCKETS:
        if d >= lo and (hi is None or d <= hi):
            return label
    return HOLDING_BUCKETS[-1][0]


def equity_curve(trades: Sequence[ClosedTrade]) -> list[dict[str, Any]]:
    """Cumulative realised P&L by exit date, with the rupee drawdown from its running peak."""
    by_day: dict[str, float] = defaultdict(float)
    for t in trades:
        by_day[t.sell_date.isoformat()] += t.pnl
    out, cum, peak = [], 0.0, 0.0
    for d in sorted(by_day):
        cum += by_day[d]
        peak = max(peak, cum)
        out.append({"date": d, "cum_pnl": cum, "drawdown": cum - peak})
    return out


def _trade_row(t: ClosedTrade) -> dict[str, Any]:
    return {
        "symbol": t.symbol,
        "exchange": t.exchange,
        "sell_date": t.sell_date.isoformat(),
        "quantity": t.quantity,
        "pnl": t.pnl,
        "pnl_pct": t.pnl_pct,
        "holding_days": t.holding_days,
    }


def _headline(trades: Sequence[ClosedTrade]) -> dict[str, Any]:
    n = len(trades)
    gains = [t.pnl for t in trades if t.is_win]
    losses = [-t.pnl for t in trades if t.is_loss]
    total = sum(t.pnl for t in trades)
    avg_win = sum(gains) / len(gains) if gains else None
    avg_loss = sum(losses) / len(losses) if losses else None
    return {
        "closed_trades": n,
        "winning_trades": len(gains),
        "losing_trades": len(losses),
        "breakeven_trades": n - len(gains) - len(losses),
        "win_rate": len(gains) / n if n else None,
        "profit_factor": sum(gains) / sum(losses) if losses else None,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff_ratio": avg_win / avg_loss if avg_win is not None and avg_loss else None,
        "expectancy": total / n if n else None,
        "total_pnl": total,
        "avg_holding_days": sum(t.holding_days for t in trades) / n if n else None,
    }


def trade_analytics(trades: Sequence[ClosedTrade], top_n: int = 5) -> dict[str, Any]:
    """Win rate, profit factor, expectancy, curves and breakdowns for one pool."""
    winners = sorted((t for t in trades if t.is_win), key=lambda t: t.pnl, reverse=True)
    losers = sorted((t for t in trades if t.is_loss), key=lambda t: t.pnl)
    months = sorted({t.sell_date.strftime("%Y-%m") for t in trades})
    return {
        **_headline(trades),
        "equity_curve": equity_curve(trades),
        "distribution": _bucketed(
            trades, _distribution_key, [b[0] for b in DISTRIBUTION_BUCKETS]
        ),
        "monthly": _bucketed(trades, lambda t: t.sell_date.strftime("%Y-%m"), months),
        "by_weekday": _bucketed(trades, lambda t: WEEKDAYS[t.sell_date.weekday()], WEEKDAYS),
        "by_holding": _bucketed(trades, _holding_key, [b[0] for b in HOLDING_BUCKETS]),
        "top_winners": [_trade_row(t) for t in winners[:top_n]],
        "top_losers": [_trade_row(t) for t in losers[:top_n]],
    }


def pool_summary(trades: Sequence[ClosedTrade]) -> dict[str, Any]:
    """Count, wins, win rate and net P&L: how R9 reports the intraday pool (no 'invested')."""
    s = _group_stats(trades)
    return {"trades": s["trades"], "wins": s["wins"], "win_rate": s["win_rate"], "net_pnl": s["pnl"]}
