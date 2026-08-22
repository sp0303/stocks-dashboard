"""FIFO engine correctness — the most important unit in the system."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.engine import compute_positions


def T(symbol, ttype, qty, price, date, charges=0.0, t="09:00:00"):
    return {
        "symbol": symbol, "trade_type": ttype, "quantity": qty, "price": price,
        "trade_date": date, "charges": charges, "order_execution_time": f"{date}T{t}",
    }


def test_simple_realized_pnl():
    trades = [T("INFY", "buy", 100, 100, "2025-01-01"),
              T("INFY", "sell", 100, 130, "2025-02-01")]
    positions, realized = compute_positions(trades)
    assert realized == 3000.0
    p = positions[0]
    assert p.quantity == 0


def test_fifo_partial_sell():
    # buy 100@1400, buy 50@1450, sell 70@1550 -> 80 open, realized from oldest lot
    trades = [T("INFY", "buy", 100, 1400, "2025-01-01"),
              T("INFY", "buy", 50, 1450, "2025-01-02"),
              T("INFY", "sell", 70, 1550, "2025-01-03")]
    positions, realized = compute_positions(trades)
    p = positions[0]
    assert p.quantity == 80
    # realized = 70 * (1550 - 1400)
    assert realized == 70 * (1550 - 1400)
    # remaining cost basis = 30@1400 + 50@1450
    assert round(p.invested_value, 2) == round(30 * 1400 + 50 * 1450, 2)
    assert round(p.avg_cost, 2) == round((30 * 1400 + 50 * 1450) / 80, 2)


def test_charges_folded_into_basis():
    # buy 10@100 +50 charges -> unit cost 105; sell 10@120 -30 charges -> proceeds 1170
    trades = [T("X", "buy", 10, 100, "2025-01-01", charges=50),
              T("X", "sell", 10, 120, "2025-02-01", charges=30)]
    _, realized = compute_positions(trades)
    assert realized == (120 * 10 - 30) - (100 * 10 + 50)  # 1170 - 1050 = 120


def test_chronological_ordering_independent_of_input_order():
    trades = [T("A", "sell", 10, 130, "2025-02-01"),
              T("A", "buy", 10, 100, "2025-01-01")]  # given out of order
    _, realized = compute_positions(trades)
    assert realized == 300.0


def test_multiple_symbols_isolated():
    trades = [T("A", "buy", 10, 100, "2025-01-01"),
              T("B", "buy", 5, 200, "2025-01-01"),
              T("A", "sell", 10, 110, "2025-01-02")]
    positions, realized = compute_positions(trades)
    assert realized == 100.0
    b = next(p for p in positions if p.symbol == "B")
    assert b.quantity == 5
