"""Endpoint tests for dividends, manual trades and the screener (no database: deps overridden)."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pi_api.core.db import get_db_connection
from pi_api.main import app
from pi_api.modules.auth.service import create_access_token
from pi_api.modules.ledger import router as ledger_router
from pi_api.modules.research import router as research_router
from pi_api.modules.research.screener import normalise_snapshot

CLIENT_ID = uuid.uuid4()
MGR_ID = uuid.uuid4()


async def _fake_conn():
    yield object()


@pytest.fixture()
def api(monkeypatch):
    app.dependency_overrides[get_db_connection] = _fake_conn

    async def allow(conn, client_id, role, manager_id, principal_client_id):
        return client_id == CLIENT_ID

    monkeypatch.setattr(
        ledger_router.portfolio_service, "validate_client_access", allow
    )
    yield TestClient(app)
    app.dependency_overrides.pop(get_db_connection, None)


def _hdr(role="manager"):
    token, _ = create_access_token(user_id=uuid.uuid4(), role=role, manager_id=MGR_ID)
    return {"Authorization": f"Bearer {token}"}


def test_dividends_requires_auth(api):
    assert api.get(f"/api/v1/ledger/dividends?client_id={CLIENT_ID}").status_code in (
        401,
        403,
    )


def test_dividends_empty_list(api, monkeypatch):
    async def none(conn, cid):
        return []

    monkeypatch.setattr(ledger_router.service, "list_dividends", none)
    r = api.get(f"/api/v1/ledger/dividends?client_id={CLIENT_ID}", headers=_hdr())
    assert r.status_code == 200 and r.json() == []


def test_dividends_forbidden_for_other_client(api):
    r = api.get(f"/api/v1/ledger/dividends?client_id={uuid.uuid4()}", headers=_hdr())
    assert r.status_code == 403


def test_add_dividend_validates_and_creates(api, monkeypatch):
    async def add(conn, data):
        return {
            **data,
            "dividend_id": 7,
            "amount": data["amount_per_share"] * data["quantity"],
            "source": "manual",
        }

    monkeypatch.setattr(ledger_router.service, "add_dividend", add)
    body = {
        "client_id": str(CLIENT_ID),
        "symbol": "ITC",
        "ex_date": "2026-06-01",
        "amount_per_share": 6.5,
        "quantity": 100,
    }
    r = api.post("/api/v1/ledger/dividends", json=body, headers=_hdr())
    assert r.status_code == 201
    assert r.json()["amount"] == pytest.approx(650.0)
    bad = api.post(
        "/api/v1/ledger/dividends", json={**body, "quantity": 0}, headers=_hdr()
    )
    assert bad.status_code == 422


def test_delete_non_manual_dividend_conflicts(api, monkeypatch):
    async def owner(conn, did):
        return {"client_id": CLIENT_ID, "source": "nse"}

    monkeypatch.setattr(ledger_router.service, "get_dividend_owner", owner)
    assert api.delete("/api/v1/ledger/dividends/1", headers=_hdr()).status_code == 409


def test_manual_trade_create(api, monkeypatch):
    seen = {}

    async def add(conn, data, recompute):
        seen.update(data)
        return {"trade_id": 42, "created": True, "recomputed": True}

    monkeypatch.setattr(ledger_router.service, "add_manual_trade", add)
    body = {
        "client_id": str(CLIENT_ID),
        "symbol": "tcs",
        "trade_date": "2026-05-04",
        "trade_type": "buy",
        "quantity": 10,
        "price": 3500.5,
    }
    r = api.post("/api/v1/ledger/trades/manual", json=body, headers=_hdr())
    assert r.status_code == 201 and r.json()["trade_id"] == 42
    assert seen["exchange"] == "NSE"
    assert (
        api.post(
            "/api/v1/ledger/trades/manual",
            json={**body, "trade_type": "BUY"},
            headers=_hdr(),
        ).status_code
        == 422
    )


def test_void_broker_trade_conflicts(api, monkeypatch):
    async def owner(conn, tid):
        return {"client_id": CLIENT_ID, "source": "upload", "deleted_at": None}

    monkeypatch.setattr(ledger_router.service, "get_trade_owner", owner)
    assert api.delete("/api/v1/ledger/trades/5", headers=_hdr()).status_code == 409


def test_void_manual_trade(api, monkeypatch):
    async def owner(conn, tid):
        return {"client_id": CLIENT_ID, "source": "manual", "deleted_at": None}

    async def void(conn, tid, cid, recompute):
        return {"trade_id": tid, "voided": True, "recomputed": False}

    monkeypatch.setattr(ledger_router.service, "get_trade_owner", owner)
    monkeypatch.setattr(ledger_router.service, "void_manual_trade", void)
    r = api.delete("/api/v1/ledger/trades/5", headers=_hdr())
    assert r.status_code == 200 and r.json()["voided"] is True


def test_void_already_voided_is_404(api, monkeypatch):
    async def owner(conn, tid):
        return {
            "client_id": CLIENT_ID,
            "source": "manual",
            "deleted_at": datetime.now(timezone.utc),
        }

    monkeypatch.setattr(ledger_router.service, "get_trade_owner", owner)
    assert api.delete("/api/v1/ledger/trades/5", headers=_hdr()).status_code == 404


def test_screener_latest_requires_auth(api):
    assert api.get("/api/v1/research/screener/latest").status_code in (401, 403)


def test_screener_latest_empty(api, monkeypatch):
    async def latest(conn, model):
        return {"as_of": None, "model": None, "count": 0, "rows": []}

    monkeypatch.setattr(research_router.service, "get_latest_screener", latest)
    r = api.get("/api/v1/research/screener/latest", headers=_hdr())
    assert r.status_code == 200 and r.json()["rows"] == []


def test_normalise_snapshot_converts_percent_to_decimal():
    payload = {
        "stocks": [
            {
                "ticker": "abc",
                "sector": "IT",
                "score": 7.5,
                "d1": 1.5,
                "w1": -2,
                "m1": 0,
                "setup": "Near breakout",
                "plan": {"expected_hold_days": 8},
            },
            {"ticker": "XYZ", "setup": None, "d1": None},
            {"name": "no ticker"},
        ]
    }
    rows = normalise_snapshot(payload)
    assert [r["symbol"] for r in rows] == ["ABC", "XYZ"]
    assert rows[0]["d1"] == pytest.approx(0.015)
    assert rows[0]["m1"] == 0.0  # R12: zero is a value, not missing
    assert rows[0]["typical_hold_days"] == 8
    assert rows[1]["setup"] is None and rows[1]["typical_hold_days"] is None


def test_normalise_snapshot_decimal_units_untouched():
    rows = normalise_snapshot(
        {"units": "decimal", "rows": [{"symbol": "A", "w1": 0.02}]}
    )
    assert rows[0]["w1"] == pytest.approx(0.02)
    assert (
        normalise_snapshot(None) == []
        and normalise_snapshot([{"symbol": "B"}])[0]["symbol"] == "B"
    )


def test_dividend_schema_rejects_bad_date(api):
    body = {
        "client_id": str(CLIENT_ID),
        "symbol": "ITC",
        "ex_date": "nope",
        "amount_per_share": 1,
        "quantity": 1,
    }
    assert (
        api.post("/api/v1/ledger/dividends", json=body, headers=_hdr()).status_code
        == 422
    )
