"""ORB endpoints: auth guard (no DB needed) and the pure view helpers."""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from pi_api.main import app
from pi_api.modules.auth.service import create_access_token
from pi_api.modules.orb import service as s

client = TestClient(app)
PATHS = ["/api/v1/orb/universe", "/api/v1/orb/signals", "/api/v1/orb/health",
         "/api/v1/orb/journal"]


@pytest.mark.parametrize("path", PATHS)
def test_orb_requires_authentication(path):
    assert client.get(path).status_code in (401, 403)


@pytest.mark.parametrize("path", PATHS)
def test_orb_rejects_bad_token(path):
    r = client.get(path, headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


@pytest.mark.parametrize("path", PATHS)
def test_orb_forbids_client_role(path):
    token, _ = create_access_token(user_id=uuid.uuid4(), role="client", client_id=uuid.uuid4())
    assert client.get(path, headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_orb_paths_in_openapi():
    paths = client.get("/openapi.json").json()["paths"]
    assert all(p in paths for p in PATHS)


def test_screen_row_converts_paise_and_percent():
    row = s.screen_row({"sym": "AAA", "passed": True, "or_high": 101050, "or_low": 100000,
                        "or_width_pct": 1.05, "rvol": 2.4, "turnover_cr": 12.3, "trace": ["x"]})
    assert row["or_high"] == 1010.5 and row["or_low"] == 1000.0
    assert row["or_width"] == pytest.approx(0.0105)  # decimal (R12)
    assert "trace" not in row  # rule traces are not exposed


def test_exit_test_needs_five_passing_sessions():
    four = [{"agree_ratio": 0.999}] * 4
    assert s.exit_test(four)["passed"] is False
    five = four + [{"agree_ratio": 0.996}]
    assert s.exit_test(five)["passed"] is True
    bad = five[:4] + [{"agree_ratio": 0.99}]
    out = s.exit_test(bad)
    assert out["passed"] is False and out["worst_agree_ratio"] == 0.99


def test_exit_test_zero_is_a_value_not_missing():
    out = s.exit_test([{"agree_ratio": 0.0}] * 5)
    assert out["sessions_scored"] == 5 and out["worst_agree_ratio"] == 0.0


def test_journal_view_curve_and_win_rate():
    base = {"reason": "t1", "side": 1, "minute": 600, "qty": 1, "price_paise": 100,
            "entry_paise": 90, "stop_paise": 80, "config": "v3"}
    trades = [{**base, "trade_date": date(2026, 10, 1), "sym": "A", "r": 1.0},
              {**base, "trade_date": date(2026, 10, 1), "sym": "B", "r": -0.5}]
    out = s.journal_view(trades, date(2026, 9, 1))
    assert out["count"] == 2 and out["total_r"] == 0.5
    assert out["win_rate"] == 0.5 and out["expectancy_r"] == 0.25
    assert [t["cum_r"] for t in out["trades"]] == [1.0, 0.5]
    assert out["trades"][0]["side"] == "LONG" and out["trades"][0]["time"] == "10:00"


def test_empty_journal_has_no_rates():
    out = s.journal_view([], date(2026, 9, 1))
    assert out["count"] == 0 and out["win_rate"] is None and out["expectancy_r"] is None
