"""Deleting an upload removes only the trades it brought in, keeps the record as DELETED,
and lets the same file be uploaded again."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services import ingestion


def _trade(n, day="2026-10-06"):
    return {"symbol": "INFY", "exchange": "NSE", "segment": "EQ", "trade_date": day,
            "trade_type": "buy", "quantity": 1, "price": 1500.0, "trade_id": str(n),
            "order_id": str(n), "fingerprint": f"fp{n}"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "adminpass")
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    batch = {"v": []}
    monkeypatch.setattr(ingestion, "parse_tradebook", lambda *_a, **_k: ingestion.ParsedTradebook(
        client_id="AB1234", date_from="2026-10-01", date_to="2026-10-31",
        trades=[dict(t) for t in batch["v"]], errors=[], file_client_id="AB1234"))
    from app.main import app
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"role": "admin", "password": "adminpass"}).json()["data"]["token"]}
        mid = c.post("/api/admin/managers", json={"name": "M", "email": "m@x.io"}, headers=h).json()["data"]["id"]
        cid = c.post("/api/clients", json={"name": "C", "portfolio_manager_id": mid, "client_code": "AB1234"},
                     headers=h).json()["data"]["id"]
        yield c, h, cid, batch


def _up(c, h, cid, body):
    return c.post(f"/api/clients/{cid}/tradebooks", files={"file": ("tb.xlsx", body, "application/octet-stream")}, headers=h)


def _fps(c, h, cid):
    return sorted(t["fingerprint"] for t in c.get(f"/api/clients/{cid}/trades", headers=h).json()["data"])


def test_delete_removes_only_that_uploads_trades(setup):
    c, h, cid, batch = setup
    batch["v"] = [_trade(1), _trade(2)]
    first = _up(c, h, cid, b"a").json()["data"]["upload"]["id"]
    batch["v"] = [_trade(2), _trade(3)]                     # fp2 is a duplicate: stays with the first
    second = _up(c, h, cid, b"b").json()["data"]["upload"]["id"]
    ups = {u["id"]: u for u in c.get(f"/api/clients/{cid}/tradebooks", headers=h).json()["data"]}
    assert ups[first]["trade_count"] == 2 and ups[second]["trade_count"] == 1

    r = c.delete(f"/api/clients/{cid}/tradebooks/{second}", headers=h)
    assert r.status_code == 200 and r.json()["data"]["trades_removed"] == 1
    assert _fps(c, h, cid) == ["fp1", "fp2"]
    ups = {u["id"]: u for u in c.get(f"/api/clients/{cid}/tradebooks", headers=h).json()["data"]}
    assert ups[second]["status"] == "DELETED" and ups[second]["trade_count"] == 0

    assert c.delete(f"/api/clients/{cid}/tradebooks/{second}", headers=h).status_code == 404
    assert _up(c, h, cid, b"b").status_code == 200          # same file is accepted again
    assert _fps(c, h, cid) == ["fp1", "fp2", "fp3"]


def test_unknown_upload_is_404(setup):
    c, h, cid, _ = setup
    assert c.delete(f"/api/clients/{cid}/tradebooks/nope", headers=h).status_code == 404
