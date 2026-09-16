"""Auth: login flows + isolation — a manager can only reach their own clients, admin sees all,
and unauthenticated requests are rejected. Isolated JsonStore, no network."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "mongodb_url", "")
    monkeypatch.setattr(settings, "data_dir", str(tmp_path))
    monkeypatch.setattr(settings, "admin_password", "adminpass")
    monkeypatch.setattr(settings, "default_manager_password", "changeme123")
    monkeypatch.setattr(settings, "auth_secret", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _admin(c):
    r = c.post("/api/auth/login", json={"role": "admin", "password": "adminpass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def _mk_manager(c, admin_h, name, email):
    r = c.post("/api/admin/managers", json={"name": name, "email": email}, headers=admin_h)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def test_admin_login_password_gate(app_client):
    assert app_client.post("/api/auth/login", json={"role": "admin", "password": "nope"}).status_code == 401
    assert app_client.post("/api/auth/login", json={"role": "admin", "password": "adminpass"}).status_code == 200


def test_admin_routes_require_admin(app_client):
    assert app_client.get("/api/admin/managers").status_code == 401          # no token
    admin_h = _admin(app_client)
    assert app_client.get("/api/admin/managers", headers=admin_h).status_code == 200


def test_manager_login_with_default_password(app_client):
    admin_h = _admin(app_client)
    _mk_manager(app_client, admin_h, "Bob", "bob@t.co")
    ok = app_client.post("/api/auth/login", json={"role": "manager", "email": "bob@t.co", "password": "changeme123"})
    assert ok.status_code == 200 and ok.json()["data"]["role"] == "manager"
    assert app_client.post("/api/auth/login", json={"role": "manager", "email": "bob@t.co", "password": "x"}).status_code == 401
    # email is required to create a manager
    assert app_client.post("/api/admin/managers", json={"name": "NoEmail"}, headers=admin_h).status_code == 400


def test_manager_sees_only_own_clients(app_client):
    admin_h = _admin(app_client)
    m_a = _mk_manager(app_client, admin_h, "A", "a@t.co")
    m_b = _mk_manager(app_client, admin_h, "B", "b@t.co")

    def mgr_headers(email):
        r = app_client.post("/api/auth/login", json={"role": "manager", "email": email, "password": "changeme123"})
        return {"Authorization": f"Bearer {r.json()['data']['token']}"}
    ha, hb = mgr_headers("a@t.co"), mgr_headers("b@t.co")

    # A creates a client under themselves — fine
    r = app_client.post("/api/clients", json={"name": "A-client", "portfolio_manager_id": m_a}, headers=ha)
    assert r.status_code == 200, r.text
    cid = r.json()["data"]["id"]

    # A cannot create a client under B
    assert app_client.post("/api/clients", json={"name": "x", "portfolio_manager_id": m_b}, headers=ha).status_code == 403
    # B cannot read A's manager book or A's client
    assert app_client.get(f"/api/managers/{m_a}/clients", headers=hb).status_code == 403
    assert app_client.get(f"/api/clients/{cid}", headers=hb).status_code == 403
    assert app_client.get(f"/api/clients/{cid}/holdings", headers=hb).status_code == 403
    # A can read their own client; admin can read anything
    assert app_client.get(f"/api/clients/{cid}", headers=ha).status_code == 200
    assert app_client.get(f"/api/clients/{cid}", headers=admin_h).status_code == 200


def test_manager_change_password(app_client):
    admin_h = _admin(app_client)
    _mk_manager(app_client, admin_h, "C", "c@t.co")
    h = {"Authorization": f"Bearer {app_client.post('/api/auth/login', json={'role':'manager','email':'c@t.co','password':'changeme123'}).json()['data']['token']}"}
    assert app_client.post("/api/auth/change-password", json={"old_password": "changeme123", "new_password": "newpass1"}, headers=h).status_code == 200
    # old no longer works, new does
    assert app_client.post("/api/auth/login", json={"role": "manager", "email": "c@t.co", "password": "changeme123"}).status_code == 401
    assert app_client.post("/api/auth/login", json={"role": "manager", "email": "c@t.co", "password": "newpass1"}).status_code == 200
