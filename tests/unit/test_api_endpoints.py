"""Unit tests for FastAPI endpoints."""

from fastapi.testclient import TestClient
from pi_api.main import app

client = TestClient(app)


def test_healthz_endpoint():
    """Verify /healthz returns 200 OK and valid JSON."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_api_v1_healthz():
    """Verify /api/v1/healthz also responds."""
    response = client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_json_available():
    """Verify OpenAPI schema is auto-generated properly."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Portfolio Intelligence API"
    assert "/api/v1/portfolio/clients" in schema["paths"]
    assert "/api/v1/ledger/trades" in schema["paths"]
    assert "/api/v1/market/securities/search" in schema["paths"]
    assert "/api/v1/research/board" in schema["paths"]


def test_market_calendar_endpoint():
    """Verify market calendar endpoint responds."""
    response = client.get("/api/v1/market/calendar")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_securities_search_endpoint():
    """Verify securities search query requires q."""
    response = client.get("/api/v1/market/securities/search?q=RELIANCE")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_benchmarks_health_endpoint():
    """Verify benchmark health monitoring endpoint."""
    response = client.get("/api/v1/market/benchmarks/health")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


import uuid
from pi_api.modules.auth.service import create_access_token


def test_portfolio_clients_unauthenticated_fails():
    """Verify accessing /portfolio/clients without auth header is rejected."""
    response = client.get("/api/v1/portfolio/clients")
    assert response.status_code in (401, 403)


def test_ledger_trades_unauthenticated_fails():
    """Verify accessing /ledger/trades without auth header is rejected."""
    response = client.get("/api/v1/ledger/trades")
    assert response.status_code in (401, 403)


def test_ledger_trades_client_role_forbidden():
    """Verify client role cannot access manager ledger routes."""
    token, _ = create_access_token(user_id=uuid.uuid4(), role="client", client_id=uuid.uuid4())
    response = client.get(
        "/api/v1/ledger/trades",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_ledger_trades_requires_client_id():
    """Verify authenticated manager receives 422 for missing client_id."""
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=uuid.uuid4())
    response = client.get(
        "/api/v1/ledger/trades",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422  # Unprocessable Entity (missing query param)


def test_admin_overview_requires_super_admin():
    """Verify admin endpoints reject manager role."""
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=uuid.uuid4())
    response = client.get(
        "/api/v1/admin/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_admin_overview_succeeds_for_super_admin():
    """Verify super_admin can query admin platform overview."""
    token, _ = create_access_token(user_id=uuid.uuid4(), role="super_admin")
    response = client.get(
        "/api/v1/admin/overview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_market_value" in data
    assert "manager_count" in data


def test_manager_holdings_endpoint_structure():
    """Verify manager holdings endpoint returns list for authorized manager."""
    mgr_id = uuid.uuid4()
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=mgr_id)
    response = client.get(
        f"/api/v1/portfolio/managers/{mgr_id}/holdings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_manager_metrics_endpoint_structure():
    """Verify manager metrics returns aggregated book structure (Rule R5)."""
    mgr_id = uuid.uuid4()
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=mgr_id)
    response = client.get(
        f"/api/v1/portfolio/managers/{mgr_id}/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_capital_deployed" in data
    assert "total_market_value" in data
    assert "return_on_capital" in data


def test_manager_trades_endpoint():
    """Verify manager trades returns trade log for authorized manager."""
    mgr_id = uuid.uuid4()
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=mgr_id)
    response = client.get(
        "/api/v1/ledger/manager-trades",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_corporate_actions_endpoint():
    """Verify corporate actions endpoint returns list of corporate events."""
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=uuid.uuid4())
    response = client.get(
        "/api/v1/ledger/corporate-actions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)



def test_benchmark_series_endpoint():
    """Verify benchmark series endpoint returns historical series (Rule R10)."""
    response = client.get("/api/v1/market/benchmarks/NIFTY_50_TRI/series")
    assert response.status_code == 200
    assert isinstance(response.json(), list)



