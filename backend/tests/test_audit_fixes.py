"""Fixes from the Nov-2026 client audit: XIRR is withheld under a year (R4) and a rights
entitlement is never valued as a holding (R6/R8)."""
from datetime import date
from unittest.mock import patch

from app.services import analytics


def _t(sym, day, side, qty, price):
    return {"symbol": sym, "trade_date": day, "trade_type": side, "quantity": qty,
            "price": price, "trade_value": qty * price}


def _quotes(prices):
    return lambda symbols, *_a, **_k: {s: {"price": prices[s], "stale": False} for s in symbols if s in prices}


def test_xirr_withheld_under_a_year():
    trades = [_t("A", "2026-02-25", "buy", 10, 100)]
    with patch.object(analytics, "get_quotes", _quotes({"A": 130.0})):
        assert analytics.portfolio_xirr(trades, today=date(2026, 11, 1)) is None


def test_xirr_reported_after_a_year():
    trades = [_t("A", "2025-01-01", "buy", 10, 100)]
    with patch.object(analytics, "get_quotes", _quotes({"A": 120.0})):
        r = analytics.portfolio_xirr(trades, today=date(2026, 11, 1))
    assert r is not None and r > 0


def test_rights_entitlement_left_out_of_cost_and_value():
    trades = [_t("OLAELEC", "2026-03-01", "buy", 10, 30), _t("OLAELEC-RE", "2026-03-02", "buy", 200, 2.33)]
    with patch.object(analytics, "get_quotes", _quotes({"OLAELEC": 40.0, "OLAELEC-RE": 1.5})):
        data = analytics.build_holdings(trades)
    tot = data["totals"]
    assert tot["invested_value"] == 300.0 and tot["market_value"] == 400.0
    assert tot["unpriced_symbols"] == ["OLAELEC-RE"]
    re = next(h for h in data["holdings"] if h["symbol"] == "OLAELEC-RE")
    assert re["rights_entitlement"] is True and re["market_value"] is None
