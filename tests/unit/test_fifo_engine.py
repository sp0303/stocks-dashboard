"""Unit tests for the single-pass FIFO engine and matching (Rules R1, R7, R8, R16)."""

from datetime import date
import pytest

from pi_core.engine.fifo import FIFOEngine
from pi_core.engine.matching import match_trades_fifo
from pi_core.models import ActionType, CorporateAction, Side, Trade


def test_fifo_trade_matching_exhaustion():
    """Verify buys are matched in strict FIFO order and realized P&L is exact."""
    trades = [
        Trade("T1", date(2024, 1, 1), "RELIANCE", "NSE", Side.BUY, 10.0, 2000.0, charges=10.0),
        Trade("T2", date(2024, 1, 5), "RELIANCE", "NSE", Side.BUY, 10.0, 2100.0, charges=10.0),
        Trade("T3", date(2024, 1, 10), "RELIANCE", "NSE", Side.SELL, 15.0, 2500.0, charges=15.0),
    ]

    matched, unmatched, open_lots = match_trades_fifo(trades)

    assert len(unmatched) == 0
    assert len(matched) == 2

    # First matched slice: 10 shares from T1
    m1 = matched[0]
    assert m1.buy_trade_id == "T1"
    assert m1.quantity == 10.0
    assert m1.cost_basis == 20000.0 + 10.0
    assert m1.proceeds == 25000.0 - 10.0
    assert m1.realized_pnl == pytest.approx(4980.0)

    # Second matched slice: 5 shares from T2
    m2 = matched[1]
    assert m2.buy_trade_id == "T2"
    assert m2.quantity == 5.0
    assert m2.cost_basis == (5 * 2100.0) + 5.0
    assert m2.proceeds == (5 * 2500.0) - 5.0

    # Remaining open lot: 5 shares of T2
    key = ("RELIANCE", "NSE")
    assert key in open_lots
    assert len(open_lots[key]) == 1
    assert open_lots[key][0].quantity == 5.0


def test_unmatched_sell_handling_rule_r7():
    """Verify sells without buy allotment are flagged as UnmatchedSell and excluded from realized PnL."""
    trades = [
        Trade("T1", date(2024, 1, 1), "TCS", "NSE", Side.BUY, 10.0, 3000.0),
        Trade("T2", date(2024, 1, 10), "TCS", "NSE", Side.SELL, 15.0, 3500.0),  # 5 shares unmatched
    ]

    matched, unmatched, open_lots = match_trades_fifo(trades)

    assert len(matched) == 1
    assert matched[0].quantity == 10.0

    assert len(unmatched) == 1
    assert unmatched[0].quantity == 5.0
    assert unmatched[0].symbol == "TCS"
    assert unmatched[0].proceeds == 5.0 * 3500.0


def test_single_pass_engine_with_corporate_action_split_rule_r8():
    """Verify 1:5 split scales open lots on ex-date before same-day trades."""
    trades = [
        Trade("T1", date(2024, 1, 1), "INFY", "NSE", Side.BUY, 100.0, 1500.0),
        Trade("T2", date(2024, 1, 15), "INFY", "NSE", Side.SELL, 200.0, 350.0),
    ]

    # Split 1:5 on 2024-01-15 (1 share becomes 5 shares, price drops from 1500 to 300)
    actions = [
        CorporateAction("INFY", ActionType.SPLIT, date(2024, 1, 15), ratio_from=1.0, ratio_to=5.0)
    ]

    calendar = [date(2024, 1, 1), date(2024, 1, 15)]

    def price_mock(sym, exch, d):
        return 350.0 if d == date(2024, 1, 15) else 1500.0

    engine = FIFOEngine(trades, actions, price_lookup=price_mock)
    result = engine.run(calendar)

    # 100 shares split into 500 shares at cost 300
    # Sell of 200 shares at 350 gives gain of (350 - 300) * 200 = 10,000
    assert len(result.matched_trades) == 1
    assert result.matched_trades[0].quantity == 200.0
    assert result.matched_trades[0].realized_pnl == pytest.approx(10000.0)

    # Remaining lots should be 300 shares at cost 300
    key = ("INFY", "NSE")
    assert key in result.open_lots
    assert result.open_lots[key][0].quantity == 300.0
    assert result.open_lots[key][0].price == 300.0


def test_capital_deployed_recycled_money_rule_r1():
    """Verify capital deployed does not double count recycled capital."""
    # Day 1: Buy 1L
    # Day 2: Sell 1.1L (10k profit)
    # Day 3: Reinvest 1L -> Capital deployed must be 1L, NOT 2L gross bought!
    trades = [
        Trade("T1", date(2024, 1, 1), "HDFC", "NSE", Side.BUY, 100.0, 1000.0),      # 100,000
        Trade("T2", date(2024, 1, 2), "HDFC", "NSE", Side.SELL, 100.0, 1100.0),     # 110,000
        Trade("T3", date(2024, 1, 3), "HDFC", "NSE", Side.BUY, 100.0, 1000.0),      # 100,000 (reinvested)
    ]

    calendar = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
    engine = FIFOEngine(trades)
    result = engine.run(calendar)

    latest = result.latest_snapshot
    assert latest is not None
    assert latest.capital_deployed == pytest.approx(100000.0)
