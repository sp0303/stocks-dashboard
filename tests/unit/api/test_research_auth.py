"""Research routes (watchlists, board, theses) must require auth and owner scoping.

Regression: these routes were reachable without a token, and any manager_id in the
query string returned that manager's watchlists. No database: deps are overridden.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from pi_api.core.db import get_db_connection
from pi_api.main import app
from pi_api.modules.auth.service import create_access_token
from pi_api.modules.research import router as research_router

MGR_ID = uuid.uuid4()
OTHER_MGR = uuid.uuid4()
MY_CLIENT = uuid.uuid4()
WL_MINE = uuid.uuid4()
WL_OTHER = uuid.uuid4()


async def _fake_conn():
    yield object()


@pytest.fixture()
def api(monkeypatch):
    app.dependency_overrides[get_db_connection] = _fake_conn

    async def allow(conn, client_id, role, manager_id, principal_client_id):
        return client_id == MY_CLIENT and manager_id == MGR_ID

    async def owner(conn, wl_id):
        return {WL_MINE: MGR_ID, WL_OTHER: OTHER_MGR}.get(wl_id)

    async def empty(conn, owner_id):
        return []

    async def noop(*a, **k):
        return None

    async def thesis(conn, client_id, symbol):
        return None

    svc = research_router.service
    monkeypatch.setattr(research_router.portfolio_service, "validate_client_access", allow)
    monkeypatch.setattr(svc, "get_watchlist_owner", owner)
    monkeypatch.setattr(svc, "get_board_item_owner", owner)
    monkeypatch.setattr(svc, "list_watchlists", empty)
    monkeypatch.setattr(svc, "list_board", empty)
    monkeypatch.setattr(svc, "delete_watchlist_entry", noop)
    monkeypatch.setattr(svc, "get_thesis", thesis)
    yield TestClient(app)
    app.dependency_overrides.pop(get_db_connection, None)


def _hdr(role="manager", manager_id=MGR_ID):
    token, _ = create_access_token(user_id=uuid.uuid4(), role=role, manager_id=manager_id)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/research/watchlists?owner_id={MGR_ID}",
        f"/api/v1/research/board?owner_id={MGR_ID}",
        f"/api/v1/research/theses/{MY_CLIENT}/ITC",
    ],
)
def test_unauthenticated_is_rejected(api, path):
    # HTTPBearer answers 403 or 401 for a missing token depending on the FastAPI version.
    assert api.get(path).status_code in (401, 403)


def test_manager_reads_own_watchlists(api):
    r = api.get(f"/api/v1/research/watchlists?owner_id={MGR_ID}", headers=_hdr())
    assert r.status_code == 200


def test_manager_cannot_read_other_managers_watchlists(api):
    r = api.get(f"/api/v1/research/watchlists?owner_id={OTHER_MGR}", headers=_hdr())
    assert r.status_code == 403


def test_manager_cannot_read_other_managers_board(api):
    r = api.get(f"/api/v1/research/board?owner_id={OTHER_MGR}", headers=_hdr())
    assert r.status_code == 403


def test_super_admin_can_read_any_owner(api):
    r = api.get(
        f"/api/v1/research/watchlists?owner_id={OTHER_MGR}",
        headers=_hdr(role="super_admin", manager_id=None),
    )
    assert r.status_code == 200


def test_cannot_edit_other_managers_watchlist_entry(api):
    r = api.delete(f"/api/v1/research/watchlists/{WL_OTHER}/entries/ITC", headers=_hdr())
    assert r.status_code == 403


def test_can_edit_own_watchlist_entry(api):
    r = api.delete(f"/api/v1/research/watchlists/{WL_MINE}/entries/ITC", headers=_hdr())
    assert r.status_code == 204


def test_unknown_watchlist_is_404(api):
    r = api.delete(f"/api/v1/research/watchlists/{uuid.uuid4()}/entries/ITC", headers=_hdr())
    assert r.status_code == 404


def test_thesis_scoped_to_managers_clients(api):
    assert api.get(f"/api/v1/research/theses/{uuid.uuid4()}/ITC", headers=_hdr()).status_code == 403
    assert api.get(f"/api/v1/research/theses/{MY_CLIENT}/ITC", headers=_hdr()).status_code == 404
