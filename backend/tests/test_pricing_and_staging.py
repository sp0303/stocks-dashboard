"""Exchange-correct pricing, manager/client agreement, and staged capital deployment."""
import math
from unittest.mock import patch

from app.services import analytics as a
from app.services.market_data import QuoteCache


def _t(sym, day, side, qty, price, exchange="NSE"):
    return {"symbol": sym, "trade_date": day, "trade_type": side, "quantity": qty,
            "price": price, "charges": 0.0, "trade_value": qty * price, "exchange": exchange}


class _FakeProvider:
    """NSE and BSE quote the same share differently, as an illiquid BSE listing does."""
    PRICES = {("VENUSREM", "NSE"): 1797.5, ("VENUSREM", "BSE"): 1590.05}
    calls = 0

    def get_quotes(self, symbols, exchanges=None):
        _FakeProvider.calls += 1
        ex = exchanges or {}
        return {s: self.PRICES[(s, ex.get(s) or "NSE")] for s in symbols}


def test_quote_cache_does_not_mix_exchanges():
    """Whichever page loaded first used to decide the price for every other page."""
    cache = QuoteCache(_FakeProvider(), ttl=600)
    nse = cache.get(["VENUSREM"], {"VENUSREM": "NSE"})["VENUSREM"]["price"]
    bse = cache.get(["VENUSREM"], {"VENUSREM": "BSE"})["VENUSREM"]["price"]
    assert nse == 1797.5
    assert bse == 1590.05                      # was 1797.5, served from the NSE entry


def test_quote_cache_still_caches_per_exchange():
    _FakeProvider.calls = 0
    cache = QuoteCache(_FakeProvider(), ttl=600)
    cache.get(["VENUSREM"], {"VENUSREM": "BSE"})
    cache.get(["VENUSREM"], {"VENUSREM": "BSE"})
    assert _FakeProvider.calls == 1


def test_manager_values_each_client_on_its_own_exchange():
    """One client holds VENUSREM on BSE, another on NSE. Rs 4,979 was the difference."""
    clients = [
        {"id": "bse", "name": "BSE holder", "trades": [_t("VENUSREM", "2026-01-01", "buy", 24, 1500, "BSE")]},
        {"id": "nse", "name": "NSE holder", "trades": [_t("VENUSREM", "2026-01-01", "buy", 10, 1500, "NSE")]},
    ]

    def fake_quotes(symbols, exchanges=None):
        return {s: {"price": _FakeProvider.PRICES[(s, (exchanges or {}).get(s) or "NSE")], "stale": False}
                for s in symbols}

    with patch.object(a, "get_quotes", side_effect=fake_quotes):
        out = a.manager_metrics(clients)

    by = {c["id"]: c for c in out["by_client"]}
    assert math.isclose(by["bse"]["market_value"], 24 * 1590.05, abs_tol=0.01)
    assert math.isclose(by["nse"]["market_value"], 10 * 1797.5, abs_tol=0.01)
    assert math.isclose(out["totals"]["market_value"], 24 * 1590.05 + 10 * 1797.5, abs_tol=0.01)


def test_manager_row_matches_the_clients_own_page():
    """The manager table row must equal what build_holdings gives the client's dashboard."""
    trades = [_t("VENUSREM", "2026-01-01", "buy", 24, 1500, "BSE")]

    def fake_quotes(symbols, exchanges=None):
        return {s: {"price": _FakeProvider.PRICES[(s, (exchanges or {}).get(s) or "NSE")], "stale": False}
                for s in symbols}

    with patch.object(a, "get_quotes", side_effect=fake_quotes):
        page = a.build_holdings(trades)["totals"]
        row = a.manager_metrics([{"id": "c", "name": "c", "trades": trades}])["by_client"][0]

    assert row["market_value"] == page["market_value"]
    assert row["unrealized_pnl"] == page["unrealized_pnl"]


def test_unpriced_symbol_is_left_out_of_cost_and_value_alike():
    """It used to drop out of market value but stay in cost, dragging unrealized P&L down."""
    trades = [_t("GOOD", "2026-01-01", "buy", 10, 100), _t("DEAD", "2026-01-01", "buy", 10, 100)]

    def fake_quotes(symbols, exchanges=None):
        return {s: {"price": 120.0 if s == "GOOD" else None, "stale": False} for s in symbols}

    with patch.object(a, "get_quotes", side_effect=fake_quotes):
        row = a.manager_metrics([{"id": "c", "name": "c", "trades": trades}])["by_client"][0]

    assert row["invested"] == 1000.0
    assert row["market_value"] == 1200.0
    assert row["unrealized_pnl"] == 200.0          # was 200 - 1000 = -800


# ── staged deployment ───────────────────────────────────────────────────────────

DAYS = ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04", "2025-01-05"]
FLAT_THEN_UP = {"AAA": dict(zip(DAYS, [100.0, 100.0, 100.0, 100.0, 110.0]))}


def test_staged_buying_gives_the_same_pnl_as_one_lump_sum():
    """Buying 300 shares at 100 in three stages must equal buying them at once."""
    lump = [_t("AAA", DAYS[0], "buy", 300, 100)]
    staged = [_t("AAA", DAYS[0], "buy", 100, 100), _t("AAA", DAYS[1], "buy", 100, 100),
              _t("AAA", DAYS[2], "buy", 100, 100)]
    rows_l = a.daily_performance_series(lump, DAYS, FLAT_THEN_UP)
    rows_s = a.daily_performance_series(staged, DAYS, FLAT_THEN_UP)

    assert rows_l[-1]["pnl"] == rows_s[-1]["pnl"] == 3_000.0
    assert a.peak_capital_deployed(lump) == a.peak_capital_deployed(staged) == 30_000.0


def test_staged_buying_gives_the_same_return_curve_as_one_lump_sum():
    """Same price path, same fully-invested days -> same NAV. Timing of deposits must not move it."""
    lump = [_t("AAA", DAYS[0], "buy", 300, 100)]
    staged = [_t("AAA", DAYS[0], "buy", 100, 100), _t("AAA", DAYS[1], "buy", 100, 100),
              _t("AAA", DAYS[2], "buy", 100, 100)]
    nav_l = a.twr_series(a.daily_performance_series(lump, DAYS, FLAT_THEN_UP))
    nav_s = a.twr_series(a.daily_performance_series(staged, DAYS, FLAT_THEN_UP))

    assert math.isclose(nav_l[-1]["nav"], 110.0, abs_tol=1e-9)
    assert math.isclose(nav_s[-1]["nav"], 110.0, abs_tol=1e-9)


def test_staged_buying_at_rising_prices_tracks_the_stock_not_the_deposits():
    """Each tranche is bought higher; the NAV must reflect price moves only, never deposits."""
    prices = {"AAA": dict(zip(DAYS, [100.0, 110.0, 121.0, 133.1, 146.41]))}   # +10% every day
    staged = [_t("AAA", DAYS[0], "buy", 100, 100), _t("AAA", DAYS[1], "buy", 100, 110),
              _t("AAA", DAYS[2], "buy", 100, 121)]
    rows = a.daily_performance_series(staged, DAYS, prices)
    nav = a.twr_series(rows)

    assert all(math.isclose(n["ret"], 0.10, abs_tol=1e-9) for n in nav)          # +10% a day, always
    assert math.isclose(nav[-1]["nav"], 100 * 1.1 ** 4, rel_tol=1e-9)
    assert rows[-1]["pnl"] == 100 * (146.41 - 100) + 100 * (146.41 - 110) + 100 * (146.41 - 121)


# ── a frozen feed must not be served as a live price ────────────────────────────

def test_frozen_quote_is_rejected():
    """Real case: VENUSREM's NSE record last traded 12-Jun-2026 yet kept returning 1797.5."""
    from datetime import datetime
    from app.services.angel import _is_stale_quote

    now = datetime(2026, 9, 20, 9, 0, 0)
    assert _is_stale_quote({"ltp": 1797.5, "exchTradeTime": "12-Jun-2026 15:41:24"}, now=now)


def test_a_normal_or_weekend_old_quote_is_kept():
    from datetime import datetime
    from app.services.angel import _is_stale_quote

    sunday = datetime(2026, 9, 20, 9, 0, 0)
    assert not _is_stale_quote({"exchTradeTime": "18-Sep-2026 15:29:45"}, now=sunday)   # Friday close


def test_missing_or_unparseable_timestamp_is_not_treated_as_stale():
    from datetime import datetime
    from app.services.angel import _is_stale_quote

    now = datetime(2026, 9, 20)
    assert not _is_stale_quote({"ltp": 100.0}, now=now)
    assert not _is_stale_quote({"exchTradeTime": "garbage"}, now=now)
