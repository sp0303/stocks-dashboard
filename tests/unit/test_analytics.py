"""Unit tests for Analytics: segments, allocation, round-trips, and LTTB (Rules R5, R9, R167)."""

from datetime import date
import pytest

from pi_core.analytics.allocation import calculate_symbol_allocation
from pi_core.analytics.round_trips import calculate_round_trips
from pi_core.engine.matching import match_trades_fifo
from pi_core.engine.segments import separate_segments
from pi_core.models import Segment, Side, Trade
from pi_core.series.downsample import lttb_downsample


def test_segment_separation_rule_r9():
    """Verify intraday same-day trades are isolated from delivery equity."""
    trades = [
        # Delivery buy
        Trade("T1", date(2024, 1, 1), "INFY", "NSE", Side.BUY, 10.0, 1500.0, segment=Segment.EQUITY),
        # Same day buy & sell for TCS (intraday round trip)
        Trade("T2", date(2024, 1, 2), "TCS", "NSE", Side.BUY, 20.0, 3000.0, segment=Segment.EQUITY),
        Trade("T3", date(2024, 1, 2), "TCS", "NSE", Side.SELL, 20.0, 3050.0, segment=Segment.EQUITY),
        # Derivative trade
        Trade("T4", date(2024, 1, 3), "NIFTY24FUT", "NFO", Side.BUY, 50.0, 21500.0, segment=Segment.DERIVATIVE),
    ]

    delivery, intraday, derivatives = separate_segments(trades)

    assert len(delivery) == 1
    assert delivery[0].trade_id == "T1"
    assert delivery[0].symbol == "INFY"

    assert len(intraday) == 2
    assert {t.trade_id for t in intraday} == {"T2", "T3"}
    assert all(t.segment == Segment.INTRADAY for t in intraday)

    assert len(derivatives) == 1
    assert derivatives[0].trade_id == "T4"


def test_round_trip_win_rate_by_trade_rule_r167():
    """Verify win rate is calculated by distinct sell trades, not FIFO lots."""
    # 2 buys, 1 sell that exhausts both lots with a net gain -> 1 trade round trip, 100% win rate!
    trades = [
        Trade("B1", date(2024, 1, 1), "SBIN", "NSE", Side.BUY, 5.0, 500.0),
        Trade("B2", date(2024, 1, 2), "SBIN", "NSE", Side.BUY, 5.0, 510.0),
        Trade("S1", date(2024, 1, 10), "SBIN", "NSE", Side.SELL, 10.0, 600.0),
    ]

    matched_lots, _, _ = match_trades_fifo(trades)
    assert len(matched_lots) == 2  # 2 matched lots

    summary = calculate_round_trips(matched_lots)
    assert summary.total_trades_count == 1  # 1 discrete trade
    assert summary.winning_trades_count == 1
    assert summary.win_rate == 1.0  # 100% win rate (Rule R167)
    assert summary.total_realized_pnl == pytest.approx(950.0)


def test_symbol_allocation_does_not_sum_legs_rule_r5():
    """Verify symbol allocation uses peak capital deployed, never summing opposing legs."""
    trades = [
        Trade("T1", date(2024, 1, 1), "WIPRO", "NSE", Side.BUY, 100.0, 400.0),   # +40k
        Trade("T2", date(2024, 1, 5), "WIPRO", "NSE", Side.SELL, 100.0, 450.0),  # -45k
        Trade("T3", date(2024, 1, 10), "WIPRO", "NSE", Side.BUY, 100.0, 420.0),  # +42k
    ]

    allocations = calculate_symbol_allocation(trades, total_book_capital_deployed=100000.0)
    assert len(allocations) == 1
    wipro_alloc = allocations[0]
    assert wipro_alloc.symbol == "WIPRO"
    # Peak capital in Wipro was 42,000, NOT (40k + 45k + 42k = 127k)!
    assert wipro_alloc.peak_capital == pytest.approx(42000.0)


def test_lttb_downsample_preserves_peaks():
    """Verify LTTB downsampling preserves extreme points."""
    raw_data = [
        (0.0, 100.0),
        (1.0, 102.0),
        (2.0, 150.0),  # Sharp peak
        (3.0, 101.0),
        (4.0, 50.0),   # Sharp trough
        (5.0, 103.0),
        (6.0, 105.0),
    ]

    downsampled = lttb_downsample(raw_data, threshold=4)
    assert len(downsampled) == 4
    # First and last points are always retained
    assert downsampled[0] == (0.0, 100.0)
    assert downsampled[-1] == (6.0, 105.0)

    ys = [pt[1] for pt in downsampled]
    assert 150.0 in ys  # Peak preserved
    assert 50.0 in ys   # Trough preserved
