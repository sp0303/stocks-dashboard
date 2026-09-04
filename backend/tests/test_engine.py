"""FIFO engine correctness — the most important unit in the system."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.engine import compute_positions


def T(symbol, ttype, qty, price, date, charges=0.0, t="09:00:00", isin=None):
    d = {
        "symbol": symbol, "trade_type": ttype, "quantity": qty, "price": price,
        "trade_date": date, "charges": charges, "order_execution_time": f"{date}T{t}",
    }
    if isin is not None:
        d["isin"] = isin
    return d


def test_same_day_sell_before_buy_nets_out():
    # Morning SELL (09:19) then afternoon BUY (14:56) of the same scrip, same day, with
    # no prior holding: this is an intraday square-off / sell-and-rebuy that must net to
    # zero — not leave a phantom open lot plus an equal unmatched sell.
    trades = [T("WAAREEENER", "sell", 10, 2006.45, "2025-04-07", t="09:19:10"),
              T("WAAREEENER", "buy", 10, 2057.35, "2025-04-07", t="14:56:28")]
    positions, realized = compute_positions(trades)
    p = positions[0]
    assert p.quantity == 0                       # no phantom open position
    assert p.unmatched_sell_qty == 0             # sell was matched, not orphaned
    assert round(realized, 2) == round(10 * (2006.45 - 2057.35), 2)  # real (small loss)


def test_isin_reconciliation_nets_rename():
    # A ticker rename (HBLPOWER -> HBLENGINE) keeps the same ISIN. Buys under the old name
    # and sells under the new name must net into one position, not leave the old ticker
    # showing a phantom open holding.
    isin = "INE292B01021"
    trades = [T("HBLPOWER", "buy", 275, 500, "2024-01-01", isin=isin),
              T("HBLENGINE", "sell", 275, 650, "2025-06-01", isin=isin)]
    positions, realized = compute_positions(trades)
    assert len(positions) == 1                   # one reconciled security, not two
    p = positions[0]
    assert p.symbol == "HBLENGINE"               # displays the current (latest) ticker
    assert p.quantity == 0                        # fully exited, nothing open
    assert p.unmatched_sell_qty == 0
    assert round(realized, 2) == round(275 * (650 - 500), 2)


def test_different_isin_not_merged():
    # Two genuinely different securities that happen to trade near each other must NOT be
    # merged just because reconciliation is on.
    trades = [T("AAA", "buy", 10, 100, "2025-01-01", isin="INE001A01011"),
              T("BBB", "buy", 5, 200, "2025-01-01", isin="INE002B01029")]
    positions, _ = compute_positions(trades)
    assert {p.symbol for p in positions} == {"AAA", "BBB"}


def _CA(isin, symbol, ex_date, atype, mult):
    return {"isin": isin, "symbol": symbol, "ex_date": ex_date, "type": atype,
            "qty_multiplier": mult}


def test_split_scales_open_quantity_and_cost():
    # Hold 10 @ Rs 1000 (Rs 10,000 invested). A 1:5 split (Rs10->Rs2, mult 5) before today
    # makes it 50 shares @ Rs 200 — same invested value, broker-matching quantity.
    isin = "INE335Y01020"
    trades = [T("IRCTC", "buy", 10, 1000, "2021-01-01", isin=isin)]
    actions = [_CA(isin, "IRCTC", "2021-10-28", "SPLIT", 5.0)]
    positions, _ = compute_positions(trades, actions)
    p = positions[0]
    assert p.quantity == 50
    assert round(p.avg_cost, 4) == 200.0
    assert round(p.invested_value, 2) == 10000.0
    assert p.applied_actions and p.applied_actions[0]["type"] == "SPLIT"


def test_bonus_after_partial_only_scales_remaining_lots():
    # Buy 100 @ 50, sell 40 (60 left), then a 1:1 bonus (mult 2) -> 120 shares @ 25.
    isin = "INE111A01011"
    trades = [T("X", "buy", 100, 50, "2024-01-01", isin=isin),
              T("X", "sell", 40, 80, "2024-06-01", isin=isin)]
    actions = [_CA(isin, "X", "2024-08-01", "BONUS", 2.0)]
    positions, realized = compute_positions(trades, actions)
    p = positions[0]
    assert p.quantity == 120                     # 60 remaining doubled
    assert round(p.avg_cost, 4) == 25.0          # 50 / 2
    assert realized == 40 * (80 - 50)            # realized P&L untouched by later bonus


def test_buy_on_exdate_not_scaled():
    # A buy executed ON the split ex-date is already at the post-split price, so it must
    # NOT be scaled; only the pre-existing holding is.
    isin = "INE222A01012"
    trades = [T("Y", "buy", 10, 1000, "2021-01-01", isin=isin),   # pre-split -> becomes 50
              T("Y", "buy", 10, 200, "2021-10-28", isin=isin)]    # on ex-date, stays 10
    actions = [_CA(isin, "Y", "2021-10-28", "SPLIT", 5.0)]
    positions, _ = compute_positions(trades, actions)
    p = positions[0]
    assert p.quantity == 60                       # 50 (scaled) + 10 (ex-date buy, unscaled)


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


def test_unmatched_sell_does_not_fabricate_profit():
    # A sell with no buy leg (IPO allotment / tradebook gap) must NOT book its full
    # proceeds as realized profit — its cost basis is unknown, so realized stays 0
    # and the quantity/value is flagged as unmatched.
    trades = [T("NSDL", "sell", 18, 1247.35, "2025-08-26")]
    positions, realized = compute_positions(trades)
    assert realized == 0.0
    p = positions[0]
    assert p.realized_pnl == 0.0
    assert p.unmatched_sell_qty == 18
    assert round(p.unmatched_sell_value, 2) == round(18 * 1247.35, 2)


def test_partially_matched_sell_only_realizes_matched_portion():
    # Hold 10, sell 18: 10 are matched (real P&L), 8 are unmatched (no fabricated gain).
    trades = [T("Z", "buy", 10, 100, "2025-01-01"),
              T("Z", "sell", 18, 150, "2025-02-01")]
    positions, realized = compute_positions(trades)
    assert realized == 10 * (150 - 100)  # only the 10 matched shares
    p = positions[0]
    assert p.quantity == 0
    assert p.unmatched_sell_qty == 8
    assert round(p.unmatched_sell_value, 2) == round(8 * 150, 2)
