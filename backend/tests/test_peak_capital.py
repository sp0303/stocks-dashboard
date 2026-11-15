"""Peak capital at risk — the "Invested" headline and the return % denominator.

Guards the two failure modes of the `buy_total - sell_total` figure this replaced:
it went negative on a profitable recycling book, and it disagreed with the money the
investor actually put in.
"""
from unittest.mock import patch

from app.services import analytics
from app.services.analytics import peak_capital_deployed, portfolio_summary


def _t(sym, day, side, qty, price, charges=0.0):
    return {"symbol": sym, "trade_date": day, "trade_type": side, "quantity": qty,
            "price": price, "charges": charges, "trade_value": qty * price}


def test_single_buy_is_its_own_cost():
    assert peak_capital_deployed([_t("A", "2025-01-01", "buy", 100, 1000)]) == 100_000.0


def test_no_trades():
    assert peak_capital_deployed([]) == 0.0


def test_reinvested_proceeds_do_not_inflate_capital():
    """Sell A and roll the whole proceeds into B: still only 1L of own money, ever."""
    trades = [
        _t("A", "2025-01-01", "buy", 100, 1000),    # -1.0L  -> running 1.0L
        _t("A", "2025-02-01", "sell", 100, 1200),   # +1.2L  -> running -0.2L
        _t("B", "2025-02-02", "buy", 100, 1200),    # -1.2L  -> running 1.0L
    ]
    assert peak_capital_deployed(trades) == 100_000.0


def test_never_negative_on_a_recycling_book():
    """The old buy_total - sell_total reported -5,73,600 here. Peak stays at the 10L put in."""
    trades, cap = [], 1_000_000.0
    for i in range(4):
        trades.append(_t(f"S{i}", f"2024-0{i + 1}-01", "buy", 100, cap / 100))
        trades.append(_t(f"S{i}", f"2024-0{i + 2}-01", "sell", 100, cap * 1.2 / 100))
        cap *= 1.2
    buy_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "buy")
    sell_total = sum(t["trade_value"] for t in trades if t["trade_type"] == "sell")

    assert buy_total - sell_total < 0          # the old figure, negative on a winning book
    assert peak_capital_deployed(trades) == 1_000_000.0


def test_adding_capital_raises_the_peak():
    trades = [
        _t("A", "2025-01-01", "buy", 100, 1000),   # running 1.0L
        _t("B", "2025-03-01", "buy", 100, 500),    # running 1.5L  <- new high
    ]
    assert peak_capital_deployed(trades) == 150_000.0


def test_charges_count_as_money_out():
    trades = [_t("A", "2025-01-01", "buy", 100, 1000, charges=250.0)]
    assert peak_capital_deployed(trades) == 100_250.0


def test_same_day_sell_then_rebuy_nets():
    """Flows net within a day — a same-day exit and re-entry needs no new money."""
    trades = [
        _t("A", "2025-01-01", "buy", 100, 1000),
        _t("A", "2025-06-01", "sell", 100, 1000),
        _t("A", "2025-06-01", "buy", 100, 1000),
    ]
    assert peak_capital_deployed(trades) == 100_000.0


def test_same_day_rotation_between_stocks_needs_no_new_capital():
    """Sell A and buy B on one day: funded by the sale, so the peak must not double."""
    trades = [
        _t("A", "2025-01-01", "buy", 100, 1000),
        _t("A", "2025-02-01", "sell", 100, 1000),
        _t("B", "2025-02-01", "buy", 100, 1000),
    ]
    assert peak_capital_deployed(trades) == 100_000.0


def test_return_pct_uses_peak_not_open_cost_basis():
    """A closed winner plus a small open position: dividing by open cost gave 500%."""
    trades = [
        _t("A", "2024-01-01", "buy", 100, 1000),    # 1.0L in
        _t("A", "2024-06-01", "sell", 100, 1500),   # +50k realized
        _t("B", "2024-06-02", "buy", 10, 1000),     # 10k of the proceeds redeployed
    ]
    # Keep the test hermetic — build_holdings would otherwise hit the live quote feed,
    # and an unpriced position is dropped from the totals entirely.
    with patch.object(analytics, "get_quotes", return_value={"B": {"price": 1000.0, "stale": False}}):
        summary = portfolio_summary(trades, actions=[])

    assert summary["peak_capital"] == 100_000.0
    assert summary["current_invested"] == 10_000.0
    # 50k realized on 1L actually risked = 50%, not 500%.
    assert summary["return_pct"] == 50.0


# ── segment separation: F&O notional must never be read as capital ──────────────

def _fo(sym, day, side, qty, price):
    t = _t(sym, day, side, qty, price)
    t["segment"] = "FO"
    return t


def test_derivatives_are_split_out_of_equity():
    from app.services.engine import split_segments

    eq = _t("INFY", "2025-01-01", "buy", 10, 1500)
    eq["segment"] = "EQ"
    fo = _fo("NIFTY25JANFUT", "2025-01-01", "buy", 50, 23000)   # 11.5L notional, ~1.5L margin

    equity, derivatives = split_segments([eq, fo])
    assert [t["symbol"] for t in equity] == ["INFY"]
    assert [t["symbol"] for t in derivatives] == ["NIFTY25JANFUT"]


def test_missing_segment_is_treated_as_equity():
    """Rows imported before the segment field existed must not vanish from a portfolio."""
    from app.services.engine import split_segments

    legacy = _t("INFY", "2025-01-01", "buy", 10, 1500)   # no segment key at all
    blank = _t("TCS", "2025-01-02", "buy", 5, 3000)
    blank["segment"] = ""

    equity, derivatives = split_segments([legacy, blank])
    assert len(equity) == 2
    assert derivatives == []


def test_fno_notional_would_dwarf_the_equity_book():
    """The reason for the split: one futures lot's notional exceeds the whole cash book."""
    from app.services.engine import split_segments

    eq = _t("INFY", "2025-01-01", "buy", 10, 1500)       # 15,000 actually paid
    eq["segment"] = "EQ"
    fo = _fo("NIFTY25JANFUT", "2025-01-02", "buy", 50, 23000)   # 11,50,000 notional

    equity, _derivatives = split_segments([eq, fo])
    assert peak_capital_deployed(equity) == 15_000.0
    # Unsplit, the same book would claim 11.65L of capital for 15k of real money.
    assert peak_capital_deployed([eq, fo]) == 1_165_000.0
