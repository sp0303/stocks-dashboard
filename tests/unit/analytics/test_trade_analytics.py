"""Closed trades and trade analytics: R7 (matched only), win rate per trade, R12 decimals."""

import random
from datetime import date, timedelta

from pi_core.analytics.closed_trades import closed_trades_from_matches
from pi_core.analytics.trade_analytics import pool_summary, trade_analytics
from pi_core.engine.matching import match_trades_fifo
from pi_core.models import Side, Trade

D0 = date(2025, 1, 6)  # Monday


def _t(i, d, sym, side, q, p, chg=None):
    return Trade(str(i), d, sym, "NSE", side, q, p, charges=chg)


def _closed(trades):
    matched, unmatched, _ = match_trades_fifo(trades)
    return closed_trades_from_matches(matched), unmatched


def test_one_sell_over_two_lots_is_one_trade_with_weighted_days():
    ct, _ = _closed([
        _t(1, D0, "AAA", Side.BUY, 10, 100),
        _t(2, D0 + timedelta(days=10), "AAA", Side.BUY, 10, 110),
        _t(3, D0 + timedelta(days=20), "AAA", Side.SELL, 20, 120),
    ])
    assert len(ct) == 1
    t = ct[0]
    assert t.buy_trade_ids == ("1", "2")
    assert t.pnl == 20 * 120 - (1000 + 1100)
    assert abs(t.pnl_pct - 300 / 2100) < 1e-12  # decimal (R12)
    assert t.holding_days == 15.0  # (20*10 + 10*10) / 20
    assert t.avg_buy_price == 105.0


def test_unmatched_sell_is_excluded_r7():
    ct, unmatched = _closed([_t(1, D0, "IPO", Side.SELL, 5, 500)])
    assert ct == [] and len(unmatched) == 1
    assert trade_analytics(ct)["closed_trades"] == 0


def test_headline_stats_and_breakdowns():
    trades = [
        _t(1, D0, "W", Side.BUY, 1, 100), _t(2, D0 + timedelta(days=2), "W", Side.SELL, 1, 130),  # +30, Wed
        _t(3, D0, "L", Side.BUY, 1, 100), _t(4, D0 + timedelta(days=40), "L", Side.SELL, 1, 90),  # -10
        _t(5, D0, "Z", Side.BUY, 1, 100), _t(6, D0 + timedelta(days=3), "Z", Side.SELL, 1, 100),  # 0
    ]
    a = trade_analytics(_closed(trades)[0])
    assert a["closed_trades"] == 3
    assert a["winning_trades"] == 1 and a["losing_trades"] == 1 and a["breakeven_trades"] == 1
    assert abs(a["win_rate"] - 1 / 3) < 1e-12  # breakeven is neither a win nor a loss
    assert a["profit_factor"] == 3.0
    assert a["avg_win"] == 30 and a["avg_loss"] == 10 and a["payoff_ratio"] == 3.0
    assert abs(a["expectancy"] - 20 / 3) < 1e-9
    dist = {b["bucket"]: b["trades"] for b in a["distribution"]}
    assert dist == {"-10% to -5%": 1, "0% to 5%": 1, "20% to 50%": 1}
    hold = {b["bucket"]: b["trades"] for b in a["by_holding"]}
    assert hold == {"1-7 days": 2, "31-90 days": 1}
    assert [b["bucket"] for b in a["by_weekday"]] == ["Wed", "Thu", "Sat"]
    assert [r["symbol"] for r in a["top_winners"]] == ["W"]
    assert [r["symbol"] for r in a["top_losers"]] == ["L"]


def test_no_losses_profit_factor_is_none_not_infinity():
    a = trade_analytics(_closed([_t(1, D0, "A", Side.BUY, 1, 1), _t(2, D0 + timedelta(1), "A", Side.SELL, 1, 2)])[0])
    assert a["profit_factor"] is None and a["win_rate"] == 1.0


def test_equity_curve_drawdown():
    trades = [
        _t(1, D0, "A", Side.BUY, 1, 100), _t(2, D0 + timedelta(1), "A", Side.SELL, 1, 150),  # +50
        _t(3, D0, "B", Side.BUY, 1, 100), _t(4, D0 + timedelta(2), "B", Side.SELL, 1, 70),   # -30
        _t(5, D0, "C", Side.BUY, 1, 100), _t(6, D0 + timedelta(3), "C", Side.SELL, 1, 110),  # +10
    ]
    curve = trade_analytics(_closed(trades)[0])["equity_curve"]
    assert [p["cum_pnl"] for p in curve] == [50, 20, 30]
    assert [p["drawdown"] for p in curve] == [0, -30, -20]


def test_empty_pool():
    a = trade_analytics([])
    assert a["win_rate"] is None and a["expectancy"] is None and a["equity_curve"] == []
    assert pool_summary([]) == {"trades": 0, "wins": 0, "win_rate": None, "net_pnl": 0}


def test_property_totals_reconcile():
    """Random books: buckets, monthly, curve and headline all add up to the same P&L."""
    rng = random.Random(7)
    for _ in range(50):
        trades, i = [], 0
        for sym in ("A", "B", "C"):
            d = D0
            for _ in range(rng.randint(1, 6)):
                i += 1
                d += timedelta(days=rng.randint(0, 30))
                side = Side.BUY if rng.random() < 0.6 else Side.SELL
                trades.append(_t(i, d, sym, side, rng.randint(1, 20), rng.uniform(50, 150), rng.choice([None, 1.5])))
        closed, _ = _closed(trades)
        a = trade_analytics(closed)
        total = sum(t.pnl for t in closed)
        assert abs(a["total_pnl"] - total) < 1e-6
        for key in ("distribution", "monthly", "by_holding", "by_weekday"):
            assert sum(b["trades"] for b in a[key]) == len(closed)
            assert abs(sum(b["pnl"] for b in a[key]) - total) < 1e-6
        if closed:
            assert abs(a["equity_curve"][-1]["cum_pnl"] - total) < 1e-6
            assert all(p["drawdown"] <= 1e-9 for p in a["equity_curve"])
        assert a["winning_trades"] + a["losing_trades"] + a["breakeven_trades"] == len(closed)
