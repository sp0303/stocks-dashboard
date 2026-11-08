"""Admin + manager-book endpoints with the database and event bus faked."""

import uuid
from datetime import date, datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pi_api.core.db import get_db_connection
from pi_api.main import app
from pi_api.modules.admin import book_router
from pi_api.modules.admin import router as admin_router
from pi_api.modules.admin.book_service import BookError
from pi_api.modules.admin.service import AdminError, AdminService
from pi_api.modules.auth.service import create_access_token

MGR = uuid.uuid4()
NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


async def _fake_conn():
    yield object()


@pytest.fixture()
def api():
    app.dependency_overrides[get_db_connection] = _fake_conn
    yield TestClient(app)
    app.dependency_overrides.pop(get_db_connection, None)


def _hdr(role="manager", mgr=MGR):
    token, _ = create_access_token(
        user_id=uuid.uuid4(), role=role, manager_id=mgr if role == "manager" else None
    )
    return {"Authorization": f"Bearer {token}"}


def _mgr(**kw):
    return {
        "manager_id": MGR,
        "name": "SP",
        "email": "sp@x.in",
        "firm": None,
        "is_active": True,
        "client_count": 0,
        "created_at": NOW,
        **kw,
    }


def test_admin_requires_super_admin(api):
    assert api.get("/api/v1/admin/managers", headers=_hdr()).status_code == 403


def test_list_managers_includes_zero_client_manager(api, monkeypatch):
    async def fake(conn):
        return [_mgr()]

    monkeypatch.setattr(admin_router.service, "list_managers", fake)
    r = api.get("/api/v1/admin/managers", headers=_hdr("super_admin"))
    assert r.status_code == 200 and r.json()[0]["client_count"] == 0


def test_delete_manager_with_clients_is_409(api, monkeypatch):
    async def fake(conn, mid):
        raise AdminError(409, "Manager still has 2 client(s).")

    monkeypatch.setattr(admin_router.service, "delete_manager", fake)
    r = api.delete(f"/api/v1/admin/managers/{MGR}", headers=_hdr("super_admin"))
    assert r.status_code == 409


def test_ca_refresh_publishes_event(api, monkeypatch):
    sent = []

    async def pub(stream, etype, data):
        sent.append((stream, etype, data))
        return "1-0"

    monkeypatch.setattr(admin_router.service, "publisher", pub)
    r = api.post(
        "/api/v1/admin/corporate-actions/refresh",
        json={"scope": "all"},
        headers=_hdr("super_admin"),
    )
    assert r.status_code == 202 and r.json()["message_id"] == "1-0"
    assert sent[0][0] == "stream:ca:refresh" and sent[0][2]["scope"] == "all"
    bad = api.post(
        "/api/v1/admin/corporate-actions/refresh",
        json={"scope": "x"},
        headers=_hdr("super_admin"),
    )
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_ca_refresh_bus_down_is_503():
    async def pub(*a):
        raise ConnectionError("redis")

    with pytest.raises(AdminError) as e:
        await AdminService(publisher=pub).request_corporate_actions_refresh(
            "held", uuid.uuid4()
        )
    assert e.value.status == 503


def test_book_forbids_other_manager(api):
    r = api.get(f"/api/v1/book/managers/{uuid.uuid4()}/summary", headers=_hdr())
    assert r.status_code == 403


def test_book_summary_shape(api, monkeypatch):
    async def fake(conn, mid):
        return {
            "manager_id": mid,
            "as_of": date(2026, 11, 1),
            "totals": {"client_count": 0, "return_on_capital": None},
            "insights": {"unique_stocks": 0},
            "clients": [],
        }

    monkeypatch.setattr(book_router.service, "summary", fake)
    r = api.get(f"/api/v1/book/managers/{MGR}/summary", headers=_hdr())
    assert r.status_code == 200 and r.json()["totals"]["return_on_capital"] is None


def test_manager_cannot_move_client(api):
    r = api.patch(
        f"/api/v1/book/clients/{uuid.uuid4()}",
        json={"manager_id": str(uuid.uuid4())},
        headers=_hdr(),
    )
    assert r.status_code == 403


def test_delete_client_of_other_manager_forbidden(api, monkeypatch):
    async def get_client(conn, cid):
        return {"client_id": cid, "manager_id": uuid.uuid4(), "client_code": None}

    monkeypatch.setattr(book_router.service, "get_client", get_client)
    assert (
        api.delete(f"/api/v1/book/clients/{uuid.uuid4()}", headers=_hdr()).status_code
        == 403
    )


def test_create_client_conflict(api, monkeypatch):
    async def fake(conn, mid, name, code, broker):
        assert mid == MGR and code == "AB1" and name == "Asha"
        raise BookError(409, "dup")

    monkeypatch.setattr(book_router.service, "create_client", fake)
    r = api.post(
        f"/api/v1/book/managers/{MGR}/clients",
        json={"name": " Asha ", "client_code": " AB1 ", "broker": "ZERODHA"},
        headers=_hdr(),
    )
    assert r.status_code == 409
    bad = api.post(
        f"/api/v1/book/managers/{MGR}/clients",
        json={"name": "A", "broker": "FOO"},
        headers=_hdr(),
    )
    assert bad.status_code == 422
