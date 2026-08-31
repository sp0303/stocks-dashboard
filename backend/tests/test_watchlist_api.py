"""HTTP-level tests for the manager multi-watchlist endpoints.

Drives the FastAPI app through TestClient against an isolated JsonStore (temp
data_dir, no Mongo). Market-data lookups are stubbed so nothing hits the network —
these assert the router's own behaviour: default-list creation, the 10-list cap,
the delete-last guard, rename, and per-list entry isolation.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # isolate persistence
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    # no network: the entry endpoints resolve prices/history through these
    import app.routers.watchlists as wl
    monkeypatch.setattr(wl, "get_quote_details", lambda symbols, exchanges=None: {})
    monkeypatch.setattr(wl, "get_history", lambda *a, **k: {"points": []})
    from app.main import app
    with TestClient(app) as c:
        yield c


def _new_manager(client) -> str:
    r = client.post("/api/admin/managers", json={"name": "Alice"})
    assert r.status_code == 200
    return r.json()["data"]["id"]


def test_default_watchlist_is_auto_created(client):
    mid = _new_manager(client)
    r = client.get(f"/api/managers/{mid}/watchlists")
    assert r.status_code == 200
    lists = r.json()["data"]
    assert len(lists) == 1
    assert lists[0]["name"] == "Watchlist 1" and lists[0]["count"] == 0


def test_create_rename_and_entry_isolation(client):
    mid = _new_manager(client)
    lists = client.get(f"/api/managers/{mid}/watchlists").json()["data"]
    default_id = lists[0]["id"]

    # create a second list
    b = client.post(f"/api/managers/{mid}/watchlists", json={"name": "Momentum"}).json()["data"]
    assert b["name"] == "Momentum"

    # add a symbol to each list
    client.post(f"/api/managers/{mid}/watchlists/{default_id}/entries", json={"symbol": "INFY"})
    client.post(f"/api/managers/{mid}/watchlists/{b['id']}/entries", json={"symbol": "TCS"})

    d_syms = [e["symbol"] for e in client.get(f"/api/managers/{mid}/watchlists/{default_id}/entries").json()["data"]]
    m_syms = [e["symbol"] for e in client.get(f"/api/managers/{mid}/watchlists/{b['id']}/entries").json()["data"]]
    assert d_syms == ["INFY"]
    assert m_syms == ["TCS"]

    # rename reflects in the listing with the right count
    client.patch(f"/api/managers/{mid}/watchlists/{b['id']}", json={"name": "Swing"})
    by_id = {l["id"]: l for l in client.get(f"/api/managers/{mid}/watchlists").json()["data"]}
    assert by_id[b["id"]]["name"] == "Swing" and by_id[b["id"]]["count"] == 1


def test_ten_list_cap_enforced(client):
    mid = _new_manager(client)
    # one default already exists → 9 more reaches the cap of 10
    for i in range(9):
        assert client.post(f"/api/managers/{mid}/watchlists", json={"name": f"L{i}"}).status_code == 200
    assert len(client.get(f"/api/managers/{mid}/watchlists").json()["data"]) == 10
    # the 11th is rejected
    r = client.post(f"/api/managers/{mid}/watchlists", json={"name": "over"})
    assert r.status_code == 400
    assert "at most" in r.json()["detail"].lower()


def test_cannot_delete_last_watchlist(client):
    mid = _new_manager(client)
    only_id = client.get(f"/api/managers/{mid}/watchlists").json()["data"][0]["id"]
    r = client.delete(f"/api/managers/{mid}/watchlists/{only_id}")
    assert r.status_code == 400
    assert "last watchlist" in r.json()["detail"].lower()


def test_delete_non_last_watchlist(client):
    mid = _new_manager(client)
    b = client.post(f"/api/managers/{mid}/watchlists", json={"name": "Temp"}).json()["data"]
    r = client.delete(f"/api/managers/{mid}/watchlists/{b['id']}")
    assert r.status_code == 200
    remaining = [l["id"] for l in r.json()["data"]]
    assert b["id"] not in remaining and len(remaining) == 1


def test_remove_entry_from_specific_list(client):
    mid = _new_manager(client)
    default_id = client.get(f"/api/managers/{mid}/watchlists").json()["data"][0]["id"]
    client.post(f"/api/managers/{mid}/watchlists/{default_id}/entries", json={"symbol": "HDFC"})
    r = client.delete(f"/api/managers/{mid}/watchlists/{default_id}/entries/HDFC")
    assert r.status_code == 200
    assert r.json()["data"] == []


def test_unknown_manager_is_404(client):
    r = client.get("/api/managers/does-not-exist/watchlists")
    assert r.status_code == 404
