"""A tradebook for a different broker account is refused before anything is stored."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services import ingestion


def _trade(n):
    return {"symbol": "INFY", "exchange": "NSE", "segment": "EQ", "trade_date": "2026-10-06",
            "trade_type": "buy", "quantity": 1, "price": 1500.0, "trade_id": str(n),
            "order_id": str(n), "fingerprint": f"fp{n}"}


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "adminpass")
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    file_code = {"v": None}
    monkeypatch.setattr(ingestion, "parse_tradebook", lambda *_a, **_k: ingestion.ParsedTradebook(
        client_id=file_code["v"], date_from="2026-10-06", date_to="2026-10-06",
        trades=[_trade(1)], errors=[], file_client_id=file_code["v"]))
    from app.main import app
    with TestClient(app) as c:
        h = {"Authorization": "Bearer " + c.post(
            "/api/auth/login", json={"role": "admin", "password": "adminpass"}).json()["data"]["token"]}
        mid = c.post("/api/admin/managers", json={"name": "M", "email": "m@x.io"}, headers=h).json()["data"]["id"]
        cid = c.post("/api/clients", json={"name": "C", "portfolio_manager_id": mid, "client_code": "AB1234"},
                     headers=h).json()["data"]["id"]
        yield c, h, cid, file_code


def _upload(c, h, cid, body=b"x", force=False):
    url = f"/api/clients/{cid}/tradebooks" + ("?force=true" if force else "")
    return c.post(url, files={"file": ("tb.xlsx", body, "application/octet-stream")}, headers=h)


def test_other_accounts_tradebook_is_rejected_even_with_force(setup):
    c, h, cid, file_code = setup
    file_code["v"] = "ZZ9999"
    for force in (False, True):
        r = _upload(c, h, cid, force=force)
        assert r.status_code == 422 and "ZZ9999" in r.text and "AB1234" in r.text
    assert c.get(f"/api/clients/{cid}/tradebooks", headers=h).json()["data"] == []


def test_matching_account_is_accepted_case_insensitively(setup):
    c, h, cid, file_code = setup
    file_code["v"] = "ab1234"
    assert _upload(c, h, cid).status_code == 200


def test_file_without_an_account_code_is_rejected_for_a_known_account(setup):
    c, h, cid, file_code = setup
    r = _upload(c, h, cid)
    assert r.status_code == 422 and "AB1234" in r.text
    assert c.get(f"/api/clients/{cid}/tradebooks", headers=h).json()["data"] == []


def test_new_client_cannot_adopt_another_clients_account(setup):
    c, h, cid, file_code = setup
    mid = c.get(f"/api/clients/{cid}", headers=h).json()["data"]["portfolio_manager_id"]
    new = c.post("/api/clients", json={"name": "New", "portfolio_manager_id": mid}, headers=h).json()["data"]["id"]
    file_code["v"] = "ab1234"                                  # AB1234 is client C's account
    r = _upload(c, h, new)
    assert r.status_code == 422 and "AB1234" in r.text
    assert c.get(f"/api/clients/{new}/tradebooks", headers=h).json()["data"] == []
    file_code["v"] = "NEW777"                                  # an unclaimed account is adopted
    assert _upload(c, h, new).status_code == 200
    assert c.get(f"/api/clients/{new}", headers=h).json()["data"]["client_code"] == "NEW777"
