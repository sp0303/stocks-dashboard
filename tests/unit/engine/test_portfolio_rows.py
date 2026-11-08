"""API row shaping for holdings (R6): unpriced is None, never cost and 0 %."""

from datetime import date

from pi_api.modules.portfolio.repository import position_row, unpriced_keys


def _row(sym, exch, price):
    return {
        "security_id": 1, "symbol": sym, "exchange": exch, "quantity": 10.0,
        "avg_cost": 50.0, "invested": 500.0, "entry_date": date(2024, 1, 1),
        "current_price": price, "price_as_of": date(2024, 2, 1),
    }


def test_unpriced_from_engine_payload_is_not_valued_at_cost():
    keys = unpriced_keys('{"unpriced": [{"symbol": "HFCL", "exchange": "BSE"}]}')
    r = position_row(_row("HFCL", "BSE", 80.0), keys)  # stale close exists, engine said unpriced
    assert r["priced"] is False
    assert r["current_price"] is r["market_value"] is r["unrealized_pnl"] is r["return_pct"] is None


def test_no_close_is_unpriced_and_priced_row_is_valued():
    assert position_row(_row("OLAELEC", "BSE", None), set())["priced"] is False
    r = position_row(_row("CARTRADE", "NSE", 60.0), unpriced_keys(None))
    assert r["priced"] and r["market_value"] == 600.0 and r["return_pct"] == 0.2
