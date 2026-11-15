"""Tradebook re-upload: the same file is refused (409) unless force=true, and a forced
re-import still skips trades already stored. Isolated JsonStore, parser stubbed, no network."""
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
def app_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "adminpass")
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    monkeypatch.setattr(ingestion, "parse_tradebook", lambda *_a, **_k: ingestion.ParsedTradebook(
        client_id=None, date_from="2026-10-06", date_to="2026-10-06",
        trades=[_trade(1), _trade(2)], errors=[]))
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_duplicate_file_needs_force_and_still_dedupes(app_client):
    h = {"Authorization": "Bearer " + app_client.post(
        "/api/auth/login", json={"role": "admin", "password": "adminpass"}).json()["data"]["token"]}
    mid = app_client.post("/api/admin/managers", json={"name": "M", "email": "m@x.io"}, headers=h).json()["data"]["id"]
    cid = app_client.post("/api/clients", json={"name": "C", "portfolio_manager_id": mid}, headers=h).json()["data"]["id"]
    url = f"/api/clients/{cid}/tradebooks"
    files = lambda: {"file": ("tb.xlsx", b"same-bytes", "application/octet-stream")}  # noqa: E731

    r1 = app_client.post(url, files=files(), headers=h)
    assert r1.status_code == 200, r1.text
    assert r1.json()["data"]["summary"]["imported"] == 2

    r2 = app_client.post(url, files=files(), headers=h)
    assert r2.status_code == 409

    r3 = app_client.post(url + "?force=true", files=files(), headers=h)
    assert r3.status_code == 200, r3.text
    s = r3.json()["data"]["summary"]
    assert s["imported"] == 0 and s["duplicates"] == 2          # nothing stored twice
