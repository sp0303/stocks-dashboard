"""Time-weighted return series and the metrics built on it.

These cover the failures that made the charts and risk cards wrong: a series with a point
only on trade days, cash flows read as performance, a benchmark that flatlined whenever a
position closed, and risk thresholds that could never fire.
"""
import math

from app.services import analytics as a


def _t(sym, day, side, qty, price, charges=0.0):
    return {"symbol": sym, "trade_date": day, "trade_type": side, "quantity": qty,
            "price": price, "charges": charges, "trade_value": qty * price}


def _cal(*days):
    return list(days)


BUY_HOLD = [_t("AAA", "2025-01-01", "buy", 100, 1000)]
PRICES = {"AAA": {"2025-01-01": 1000.0, "2025-01-02": 1050.0, "2025-01-03": 1100.0}}
CALENDAR = _cal("2025-01-01", "2025-01-02", "2025-01-03")


# ── daily coverage ──────────────────────────────────────────────────────────────

def test_series_has_a_row_per_calendar_day_not_per_trade():
    """One trade, three market days -> three points. This used to yield one."""
    rows = a.daily_performance_series(BUY_HOLD, CALENDAR, PRICES)
    assert [r["date"] for r in rows] == CALENDAR


def test_value_moves_on_days_with_no_trades():
    rows = a.daily_performance_series(BUY_HOLD, CALENDAR, PRICES)
    assert [r["market_value"] for r in rows] == [100_000.0, 105_000.0, 110_000.0]


def test_trade_days_survive_even_if_absent_from_the_calendar():
    """A trade on a day the index map lacks must not drop out of the series."""
    rows = a.daily_performance_series(
        BUY_HOLD + [_t("AAA", "2025-01-04", "buy", 10, 1100)],
        CALENDAR,   # no 2025-01-04
        PRICES,
    )
    assert "2025-01-04" in [r["date"] for r in rows]


def test_unpriced_symbol_is_held_at_cost_not_dropped():
    rows = a.daily_performance_series(BUY_HOLD, CALENDAR, price_maps={})
    assert all(r["market_value"] == 100_000.0 for r in rows)


# ── time-weighted return ────────────────────────────────────────────────────────

def test_twr_tracks_price_only():
    nav = a.twr_series(a.daily_performance_series(BUY_HOLD, CALENDAR, PRICES))
    assert nav[-1]["nav"] == 110.0          # +10%, matching the stock


def test_buying_more_is_not_a_gain():
    """The core bug: a deposit used to register as a positive daily return.

    Value doubles on the purchase day, but the return is the price move only. The tranche
    was bought at that day's close (1050), so it earned nothing that day and adds nothing
    to the capital base: the day is +5%, exactly the stock's move.
    """
    trades = BUY_HOLD + [_t("AAA", "2025-01-02", "buy", 100, 1050)]
    rows = a.daily_performance_series(trades, CALENDAR, PRICES)
    nav = a.twr_series(rows)
    day2 = next(n for n in nav if n["date"] == "2025-01-02")
    assert math.isclose(day2["ret"], 0.05, abs_tol=1e-9)


def test_selling_everything_is_not_a_loss():
    """A full exit used to read as roughly -100% and wreck volatility and drawdown."""
    trades = BUY_HOLD + [_t("AAA", "2025-01-02", "sell", 100, 1050)]
    rows = a.daily_performance_series(trades, CALENDAR, PRICES)
    nav = a.twr_series(rows)
    assert math.isclose(nav[-1]["nav"], 105.0, abs_tol=1e-6)     # keeps the +5% earned
    assert all(n["ret"] > -0.5 for n in nav)                     # no phantom crash
    assert a.calculate_max_drawdown(nav) is None                 # and no phantom drawdown


# ── benchmark shares the portfolio's baseline ───────────────────────────────────

def test_benchmark_pnl_survives_a_closed_position():
    """Portfolio and index both rise 10%; both must report the same gain after the exit."""
    trades = BUY_HOLD + [_t("AAA", "2025-01-03", "sell", 100, 1100)]
    index = {"2025-01-01": 100.0, "2025-01-02": 105.0, "2025-01-03": 110.0}

    rows = a.daily_performance_series(trades, CALENDAR, PRICES)
    bench = a.benchmark_series(trades, index, CALENDAR)

    assert rows[-1]["pnl"] == 10_000.0
    assert bench[-1]["benchmark_pnl"] == 10_000.0   # was 0.0 — the index looked flat


def test_benchmark_beats_portfolio_is_visible():
    """Index up 20% while the stock is up 10% must show the index ahead."""
    index = {"2025-01-01": 100.0, "2025-01-02": 110.0, "2025-01-03": 120.0}
    rows = a.daily_performance_series(BUY_HOLD, CALENDAR, PRICES)
    bench = a.benchmark_series(BUY_HOLD, index, CALENDAR)
    assert bench[-1]["benchmark_pnl"] > rows[-1]["pnl"]


# ── metrics ─────────────────────────────────────────────────────────────────────

def _year_of_navs(daily_return=0.0005):
    rows, value, net = [], 100_000.0, 100_000.0
    from datetime import date, timedelta
    d = date(2024, 1, 1)
    for i in range(400):
        if i:
            value *= 1 + daily_return
        rows.append({"date": str(d), "market_value": value, "net_invested": net})
        d += timedelta(days=1)
    return a.twr_series(rows)


def test_cagr_withheld_under_one_year():
    """Annualizing a partial year invents a return, per GIPS — so it returns None."""
    nav = a.twr_series(a.daily_performance_series(BUY_HOLD, CALENDAR, PRICES))
    assert a.calculate_cagr(nav) is None
    assert a.calculate_total_return(nav) is not None      # cumulative still available


def test_cagr_computed_once_a_full_year_exists():
    assert a.calculate_cagr(_year_of_navs()) is not None


def test_sharpe_is_defined_once_and_returns_a_number():
    """There were two calculate_sharpe_ratio definitions; the live one always gave None."""
    nav = _year_of_navs()
    assert a.calculate_sharpe_ratio(nav) is not None
    assert a.calculate_sharpe_ratio.__code__.co_varnames[0] == "nav_series"


def test_beta_aligns_by_date_not_by_position():
    """Identical returns on shared dates give beta 1 even when the series differ in length."""
    port = [("2025-01-02", 0.01), ("2025-01-03", -0.02), ("2025-01-06", 0.03)]
    bench = [("2025-01-01", 0.09), ("2025-01-02", 0.01), ("2025-01-03", -0.02), ("2025-01-06", 0.03)]
    assert math.isclose(a.calculate_beta(port, bench), 1.0, abs_tol=1e-9)


def test_beta_ignores_an_unshared_date():
    port = [("2025-01-02", 0.01), ("2025-01-03", -0.02)]
    bench = [("2025-01-02", 0.01), ("2025-01-03", -0.02), ("2025-01-09", 99.0)]
    assert math.isclose(a.calculate_beta(port, bench), 1.0, abs_tol=1e-9)


def test_risk_thresholds_compare_decimals_to_decimals():
    """Volatility of 0.40 is 40% and must trip the alert; it was compared against 25."""
    from datetime import date, timedelta
    import random
    random.seed(3)
    rows, value, d = [], 100_000.0, date(2024, 1, 1)
    for _ in range(300):
        value *= 1 + random.gauss(0.0, 0.05)      # very volatile
        rows.append({"date": str(d), "market_value": value, "net_invested": 100_000.0})
        d += timedelta(days=1)
    nav = a.twr_series(rows)

    assert a.calculate_volatility(nav) > 0.25
    trades = [_t("AAA", "2024-01-01", "buy", 100, 1000)]
    assert "High volatility" in a.compute_risk_monitoring(nav, trades)["alerts"]


# ── degenerate states found only on the real book ───────────────────────────────

def test_topping_up_a_nearly_empty_portfolio_is_not_a_crash():
    """Real case: Rs 434 residual, then a Rs 3,514 purchase.

    Dividing by the pre-flow value gave a -403% daily return, drove NAV negative, and
    left 746 days of garbage behind it (max drawdown -1084%).
    """
    rows = [
        {"date": "2023-09-05", "market_value": 434.10, "net_invested": -301.35},
        {"date": "2023-09-06", "market_value": 2199.90, "net_invested": 3213.15},
    ]
    nav = a.twr_series(rows)
    assert nav[-1]["ret"] > -1.0
    assert nav[-1]["nav"] > 0


def test_nav_never_goes_non_positive():
    """NAV <= 0 is unrecoverable: every later return compounds off a negative base."""
    rows = [
        {"date": "2025-01-01", "market_value": 100.0, "net_invested": 100.0},
        {"date": "2025-01-02", "market_value": 50.0, "net_invested": 100_000.0},
        {"date": "2025-01-03", "market_value": 90_000.0, "net_invested": 100_000.0},
        {"date": "2025-01-04", "market_value": 95_000.0, "net_invested": 100_000.0},
    ]
    nav = a.twr_series(rows)
    assert all(n["nav"] > 0 for n in nav)


def test_drawdown_cannot_exceed_minus_one_hundred_percent():
    rows = [
        {"date": "2025-01-01", "market_value": 100_000.0, "net_invested": 100_000.0},
        {"date": "2025-01-02", "market_value": 1.0, "net_invested": 100_000.0},
        {"date": "2025-01-03", "market_value": 250_000.0, "net_invested": 400_000.0},
        {"date": "2025-01-04", "market_value": 260_000.0, "net_invested": 400_000.0},
    ]
    dd = a.calculate_max_drawdown(a.twr_series(rows))
    assert dd is None or dd >= -1.0


def test_adding_money_on_a_flat_day_is_a_zero_return():
    """Start-of-day flow convention: a deposit with no price move must not register."""
    rows = [
        {"date": "2025-01-01", "market_value": 100_000.0, "net_invested": 100_000.0},
        {"date": "2025-01-02", "market_value": 200_000.0, "net_invested": 200_000.0},
    ]
    assert math.isclose(a.twr_series(rows)[-1]["ret"], 0.0, abs_tol=1e-12)


# ── shares that arrive without a buy (demerger / IPO allotment / transfer-in) ───

def test_unmatched_sell_is_not_counted_as_profit():
    """Real case: RAYMONDREL credited by demerger, then sold — no buy in the tradebook.

    Its proceeds were treated as cash withdrawn, so the chart booked them as pure gain
    (a ~60% one-day jump) while the cards, which exclude unmatched sells, did not.
    """
    from app.services.engine import matched_trades, compute_positions

    trades = [
        _t("AAA", "2025-01-01", "buy", 100, 1000),
        _t("RRL", "2025-01-02", "sell", 50, 2000),      # never bought -> unmatched
    ]
    prices = {"AAA": {"2025-01-01": 1000.0, "2025-01-02": 1000.0, "2025-01-03": 1000.0}}
    cal = ["2025-01-01", "2025-01-02", "2025-01-03"]

    assert matched_trades(trades) == [trades[0]]        # the orphan sell is dropped

    rows = a.daily_performance_series(matched_trades(trades), cal, prices)
    assert rows[-1]["pnl"] == 0.0                       # was +100,000

    _, realized = compute_positions(trades)
    assert realized == 0.0                              # cards agree: no P&L booked


def test_chart_pnl_equals_realized_plus_unrealized():
    """Identity that must hold once flows only describe matched shares."""
    from app.services.engine import matched_trades, compute_positions

    trades = [
        _t("AAA", "2025-01-01", "buy", 100, 1000),
        _t("AAA", "2025-01-02", "sell", 40, 1100),
        _t("ORPHAN", "2025-01-02", "sell", 10, 500),
    ]
    prices = {"AAA": {"2025-01-01": 1000.0, "2025-01-02": 1100.0, "2025-01-03": 1200.0}}
    cal = ["2025-01-01", "2025-01-02", "2025-01-03"]

    rows = a.daily_performance_series(matched_trades(trades), cal, prices)
    positions, realized = compute_positions(trades)
    open_pos = [p for p in positions if p.quantity > 0]
    unrealized = sum(p.quantity * (1200.0 - p.avg_cost) for p in open_pos)

    assert math.isclose(rows[-1]["pnl"], realized + unrealized, abs_tol=0.01)


def test_partially_matched_sell_is_trimmed_not_dropped():
    from app.services.engine import matched_trades

    trades = [
        _t("AAA", "2025-01-01", "buy", 30, 1000),
        _t("AAA", "2025-01-02", "sell", 50, 1100),      # only 30 are matchable
    ]
    sell = matched_trades(trades)[1]
    assert sell["quantity"] == 30


def test_risk_monitoring_weights_by_market_value_when_holdings_given():
    """Sector weight must use the same basis as the Concentration panel (market value).

    Cost-weighted it read 40.9% while the panel beside it said 39.0% for the same account.
    """
    nav = _year_of_navs()
    trades = [_t("AAA", "2024-01-01", "buy", 100, 100), _t("BBB", "2024-01-01", "buy", 100, 100)]
    holdings = [
        {"symbol": "AAA", "market_value": 30_000.0, "invested_value": 10_000.0, "sector": "IT", "cap": "Large"},
        {"symbol": "BBB", "market_value": 10_000.0, "invested_value": 10_000.0, "sector": "Banks", "cap": "Large"},
    ]
    out = a.compute_risk_monitoring(nav, trades, holdings=holdings)
    assert out["concentration"]["largest_sector"] == "IT"
    assert out["concentration"]["largest_sector_pct"] == 75.0      # 30k of 40k, not 50%


# ── price basis (R17) ───────────────────────────────────────────────────────────

def test_split_adjusted_history_without_the_action_is_not_a_loss():
    """Bought at 500 while the (1:5 adjusted) history reads 100: no -80% day, flagged."""
    trades = [_t("BF", "2025-01-02", "buy", 10, 500)]
    prices = {"BF": {"2025-01-01": 98.0, "2025-01-02": 100.0, "2025-01-03": 110.0}}
    rows = a.daily_performance_series(trades, _cal("2025-01-01", "2025-01-02", "2025-01-03"), prices)
    assert rows[0]["market_value"] == 5000.0
    assert rows[-1]["market_value"] == 5500.0
    nav = a.twr_series(rows)
    assert math.isclose(nav[-1]["nav"], 110.0, rel_tol=1e-6)
    assert rows[-1]["price_basis_symbols"] == ["BF"]


def test_known_split_with_adjusted_history_needs_no_correction():
    """The engine applies the 1:2 bonus to the lots; the adjusted history already agrees."""
    trades = [_t("TM", "2025-01-02", "buy", 10, 200)]
    actions = [{"symbol": "TM", "type": "BONUS", "ex_date": "2025-01-03", "qty_multiplier": 2.0}]
    prices = {"TM": {"2025-01-02": 100.0, "2025-01-03": 105.0}}
    rows = a.daily_performance_series(trades, _cal("2025-01-02", "2025-01-03"), prices, actions)
    assert rows[0]["market_value"] == 2000.0 and rows[-1]["market_value"] == 2100.0
    assert "price_basis_symbols" not in rows[-1]


def test_normal_intraday_gap_is_not_a_basis_change():
    trades = [_t("AAA", "2025-01-02", "buy", 10, 1100)]   # 10% above the close
    rows = a.daily_performance_series(trades, CALENDAR, PRICES)
    assert rows[0]["market_value"] == 10500.0 and "price_basis_symbols" not in rows[-1]
