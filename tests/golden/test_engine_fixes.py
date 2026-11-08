"""Golden tests for the engine/pricing fixes (R2, R5, R6, R9, R16, R17).

Each scenario is the smallest book that reproduces a bug seen on the live v2 site.
The "bug" assertions run the pre-fix pipeline shape (one pool, book-level TWR with no
per-holding marks, unpriced held at cost) to show the artefact; the "fix" assertions
run ``compute_client`` as the worker does.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pytest
from pi_core.engine.fifo import FIFOEngine
from pi_core.models import Side, Trade
from pi_core.series.book import book_metrics, book_nav_series
from pi_core.series.twr import calculate_twr_series
from pi_workers.portfolio_compute import build_price_lookup, compute_client

D0 = date(2022, 1, 3)  # Monday


def days(n: int) -> list[date]:
    out, d = [], D0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def T(i, d, sym, side, q, p, exch="NSE"):
    return Trade(f"T{i}", d, sym, exch, Side.BUY if side == "B" else Side.SELL, q, p)


def flat(sym, exch, px, ds):
    return [(sym, exch, d, px) for d in ds]


def last_nav(res) -> float:
    return res.daily[-1][7]  # nav (index 7; unpriced_cost follows it)


# --- Bug 1: intraday profit booked as NAV return on a tiny delivery base -----------------


def test_intraday_round_trip_is_not_delivery_return():
    ds = days(5)
    trades = [
        T(1, ds[0], "AAA", "B", 9, 100.33),  # ~Rs 903 delivery base
        T(2, ds[1], "BBB", "B", 500, 100.0),  # same-day round trip: +Rs 2,000
        T(3, ds[1], "BBB", "S", 500, 104.0),
    ]
    prices = flat("AAA", "NSE", 100.33, ds) + flat("BBB", "NSE", 100.0, ds)
    look = build_price_lookup(prices)

    # Pre-fix shape: one pool, book-level TWR. The Rs 2,000 lands on a Rs 903 base.
    old = FIFOEngine(trades, price_lookup=look).run(ds, as_of=ds[-1])
    old_snaps = [replace(s, marks={}) for s in old.snapshots]
    old_nav, _ = calculate_twr_series(old_snaps, trades, look)
    assert old_nav[-1].nav > 300.0  # ≈ +221 %: the artefact

    res = compute_client(trades, [], look, ds[-1], set())
    assert last_nav(res) == pytest.approx(100.0)
    assert res.overview["intraday"] == {"trades": 2, "pnl": 2000.0}
    assert res.overview["capital_deployed"] == pytest.approx(903.0, abs=0.1)


# --- Bug 2: unpriced holdings must leave BOTH cost and value (R6.4) ----------------------


def test_unpriced_holding_is_excluded_and_listed():
    ds = days(3)
    trades = [
        T(1, ds[0], "AAA", "B", 10, 100.0),
        T(2, ds[0], "HFCL", "B", 20, 50.0, exch="BSE"),  # no BSE close anywhere
    ]
    look = build_price_lookup(flat("AAA", "NSE", 110.0, ds))  # HFCL: no close on any exchange
    res = compute_client(trades, [], look, ds[-1], set())
    ov = res.overview
    assert ov["market_value"] == pytest.approx(1100.0)
    assert ov["current_invested"] == pytest.approx(1000.0)
    assert ov["unrealized_pnl"] == pytest.approx(100.0)  # not diluted by a 0 % row
    assert ov["unpriced"] == [
        {"symbol": "HFCL", "exchange": "BSE", "quantity": 20.0, "cost": 1000.0}
    ]
    assert ov["unpriced_cost"] == 1000.0
    assert ov["open_positions"] == 2 and ov["priced_positions"] == 1  # bug 6
    assert [p[:2] for p in res.positions] == [("AAA", "NSE"), ("HFCL", "BSE")]
    assert any("HFCL" in w and "R6" in w for w in res.warnings)


def test_bse_lot_is_valued_at_nse_close_and_flagged_adr_0009():
    """Owner decision 2026-11-08: a BSE-bought lot with no BSE close uses the NSE close, visibly."""
    ds = days(3)
    trades = [T(1, ds[0], "HFCL", "B", 20, 50.0, exch="BSE")]
    look = build_price_lookup(flat("HFCL", "NSE", 80.0, ds))
    ov = compute_client(trades, [], look, ds[-1], set()).overview
    assert ov["market_value"] == pytest.approx(1600.0)  # 20 x 80, not left out
    assert ov["unrealized_pnl"] == pytest.approx(600.0) and ov["unpriced"] == []
    assert ov["priced_on_other_exchange"] == [{"symbol": "HFCL", "exchange": "BSE", "priced_on": "NSE"}]
    assert any("HFCL" in w and "ADR-0009" in w for w in compute_client(trades, [], look, ds[-1], set()).warnings)


def test_gaining_a_price_is_a_transfer_not_a_return():
    """Held at cost for days, then priced 3x higher: v2.1 booked +200 % in one day."""
    ds = days(6)
    trades = [
        T(1, ds[0], "AAA", "B", 10, 100.0),
        T(2, ds[0], "ILQ", "B", 10, 100.0, "BSE"),
    ]
    prices = flat("AAA", "NSE", 100.0, ds) + [("ILQ", "BSE", d, 300.0) for d in ds[3:]]
    res = compute_client(trades, [], build_price_lookup(prices), ds[-1], set())
    assert max(abs(r[6]) for r in res.daily) < 1e-9
    assert last_nav(res) == pytest.approx(100.0)
    assert res.overview["market_value"] == pytest.approx(4000.0)  # priced now: in both
    assert res.overview["current_invested"] == pytest.approx(2000.0)


# --- Bug 3: delivery shares are fungible across exchanges --------------------------------


def test_buy_on_bse_sell_on_nse_leaves_no_phantom_lot():
    ds = days(3)
    trades = [
        T(1, ds[0], "AARTIPHARM", "B", 68, 500.0, "BSE"),
        T(2, ds[2], "AARTIPHARM", "S", 68, 520.0),
    ]
    prices = flat("AARTIPHARM", "NSE", 510.0, ds) + flat("AARTIPHARM", "BSE", 510.0, ds)
    res = compute_client(trades, [], build_price_lookup(prices), ds[-1], set())
    assert res.positions == []
    assert res.overview["unmatched_sells"] == 0
    assert res.overview["realized_pnl"] == pytest.approx(68 * 20.0)


# --- R17: adjusted history next to as-traded quantities ----------------------------------


def test_unreported_split_with_adjusted_history_is_flagged_not_compounded():
    ds = days(4)
    trades = [T(1, ds[0], "SPL", "B", 10, 500.0)]
    # Vendor history already split-adjusted 1:5 from day 2; no corporate action in the feed.
    prices = [("SPL", "NSE", ds[0], 500.0), ("SPL", "NSE", ds[1], 505.0)] + flat(
        "SPL", "NSE", 101.0, ds[2:]
    )
    res = compute_client(trades, [], build_price_lookup(prices), ds[-1], set())
    assert min(r[7] for r in res.daily) > 99.0  # no −80 % day
    assert any("Price jump" in w for w in res.warnings)


# --- R2 properties survive the per-holding path ------------------------------------------


def test_staged_and_lump_sum_give_the_same_nav():
    ds = days(4)
    px = {ds[0]: 100.0, ds[1]: 110.0, ds[2]: 121.0, ds[3]: 121.0}
    prices = [("X", "NSE", d, p) for d, p in px.items()]
    look = build_price_lookup(prices)
    lump = compute_client([T(1, ds[0], "X", "B", 20, 100.0)], [], look, ds[-1], set())
    staged = compute_client(
        [T(1, ds[0], "X", "B", 10, 100.0), T(2, ds[1], "X", "B", 10, 110.0)],
        [],
        look,
        ds[-1],
        set(),
    )
    assert last_nav(lump) == pytest.approx(121.0)
    assert last_nav(staged) == pytest.approx(last_nav(lump))


def test_full_exit_is_not_a_loss_and_nav_stays_positive():
    ds = days(4)
    prices = [("X", "NSE", ds[0], 100.0), ("X", "NSE", ds[1], 110.0)] + flat(
        "X", "NSE", 110.0, ds[2:]
    )
    trades = [T(1, ds[0], "X", "B", 10, 100.0), T(2, ds[2], "X", "S", 10, 110.0)]
    res = compute_client(trades, [], build_price_lookup(prices), ds[-1], set())
    assert [round(r[7], 6) for r in res.daily] == [100.0, 110.0, 110.0, 110.0]


# --- Bug 5: book metrics from client figures (R5) ----------------------------------------


def test_book_nav_is_base_weighted_sum_of_clients():
    d1, d2, d3 = days(3)
    rows = [
        (d1, 0.0, 1000.0, 1000.0),
        (d1, 0.0, 3000.0, 3000.0),
        (d2, 0.10, 1000.0, 1100.0),
        (d2, 0.0, 3000.0, 3000.0),  # book +2.5 %
        (d3, -0.10, 1100.0, 990.0),
        (d3, 0.0, 0.5, 0.0),  # base < Rs 1 → no weight (R16)
    ]
    nav = book_nav_series(rows)
    assert [round(p.nav, 6) for p in nav] == [100.0, 102.5, 92.25]
    m = book_metrics(rows)
    assert m["book_total_return"] == pytest.approx(-0.0775)
    assert m["book_max_drawdown"] == pytest.approx(92.25 / 102.5 - 1)
    assert (
        m["book_volatility"] is not None and m["book_cagr"] is None
    )  # < 365 days (R3)
