"""'Find missing dividends': held quantity on the ex-date (R7/R8/R9), nothing auto-recorded."""

import uuid
from datetime import date as D

from fastapi.testclient import TestClient
from pi_api.modules.ledger import router as ledger_router
from pi_api.modules.ledger.dividend_suggestions import held_before, suggest


def t(d, side, q, sym="ITC", seg="EQ"):
    return {"symbol": sym, "trade_date": d, "trade_type": side, "quantity": q, "segment": seg}


def div(d, aps, sym="ITC"):
    return {"symbol": sym, "ex_date": d, "type": "DIVIDEND", "amount_per_share": aps,
            "qty_multiplier": None, "subject": "Interim dividend", "source": "NSE"}


def test_buy_on_ex_date_does_not_carry_the_dividend():
    trades = [t(D(2026, 1, 5), "buy", 10), t(D(2026, 6, 1), "buy", 5)]
    assert held_before(trades, [], D(2026, 6, 1)) == 10


def test_split_before_ex_date_scales_quantity_and_derivatives_ignored():
    trades = [t(D(2026, 1, 5), "buy", 10), t(D(2026, 2, 1), "buy", 50, seg="FO")]
    split = {"symbol": "ITC", "ex_date": D(2026, 3, 1), "type": "SPLIT", "qty_multiplier": 5.0}
    assert held_before(trades, [split], D(2026, 6, 1)) == 50


def test_unmatched_sell_never_goes_negative():
    trades = [t(D(2026, 1, 5), "sell", 10), t(D(2026, 1, 6), "buy", 3)]
    assert held_before(trades, [], D(2026, 2, 1)) == 3


def test_suggest_skips_recorded_unheld_unknown_amount_and_dedupes():
    trades = [t(D(2026, 1, 5), "buy", 10), t(D(2026, 4, 1), "sell", 10)]
    actions = [div(D(2026, 2, 1), 6.5), div(D(2026, 2, 1), 6.5),  # duplicate feed rows
               div(D(2026, 3, 1), 1.0), div(D(2026, 3, 15), None),  # unknown amount: skip (R15)
               div(D(2026, 5, 1), 2.0)]  # sold out before: skip
    out = suggest(trades, actions, existing=[("itc", D(2026, 3, 1))])
    assert [(s["ex_date"], s["estimated_quantity"], s["estimated_total"]) for s in out] == [
        (D(2026, 2, 1), 10.0, 65.0)]


def test_endpoint_is_read_only_and_checks_access(monkeypatch):
    from pi_api.core.db import get_db_connection
    from pi_api.main import app
    from pi_api.modules.auth.deps import Principal, require_manager

    cid = uuid.uuid4()
    calls = {}

    async def access(conn, client_id, principal):
        calls["access"] = client_id

    async def inputs(conn, client_id):
        return {"trades": [t(D(2026, 1, 5), "buy", 4)], "actions": [div(D(2026, 2, 1), 2.5)], "existing": []}

    async def _conn():
        yield object()

    monkeypatch.setattr(ledger_router, "_ensure_access", access)
    monkeypatch.setattr(ledger_router.service.repo, "dividend_suggestion_inputs", inputs)
    monkeypatch.setattr(ledger_router.service.repo, "insert_dividend",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not write")))
    app.dependency_overrides[get_db_connection] = _conn
    app.dependency_overrides[require_manager] = lambda: Principal.__new__(Principal)
    try:
        r = TestClient(app).get(f"/api/v1/ledger/dividends/suggestions?client_id={cid}")
        assert r.status_code == 200, r.text
        assert r.json()[0]["estimated_total"] == 10.0 and calls["access"] == cid
    finally:
        app.dependency_overrides.pop(get_db_connection, None)
        app.dependency_overrides.pop(require_manager, None)
