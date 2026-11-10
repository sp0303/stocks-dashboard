"""Heatmap service + router: exchange choice, day/range assembly, None-not-0, auth. Repo is faked."""

import asyncio
import math
import uuid
from datetime import date

from fastapi.testclient import TestClient
from pi_api.core.db import get_db_connection
from pi_api.main import app
from pi_api.modules.auth.service import create_access_token
from pi_api.modules.heatmap import router as heatmap_router
from pi_api.modules.heatmap.service import HeatmapService, pick_series

MID = uuid.uuid4()
D = date.fromisoformat


class _Repo:
    def __init__(self, holdings, closes, actions=()):
        self._h, self._c, self._a = holdings, closes, list(actions)
        self.calls = []

    async def holdings(self, _conn, manager_id, client_ids):
        self.calls.append(("holdings", manager_id, client_ids))
        return [dict(h) for h in self._h]

    async def closes(self, _conn, symbols, since, until):
        self.calls.append(("closes", since, until))
        return [
            c
            for c in self._c
            if c["symbol"] in symbols and since <= c["price_date"] <= until
        ]

    async def actions(self, _conn, symbols, since):
        return [a for a in self._a if a["symbol"] in symbols]


def _close(sym, d, c, ex="NSE"):
    return {"symbol": sym, "exchange": ex, "price_date": D(d), "close": c}


HOLD = [
    {
        "symbol": "AAA",
        "qty": 10.0,
        "invested": 1000.0,
        "clients": 2,
        "entry_date": D("2026-10-01"),
    },
    {
        "symbol": "BBB",
        "qty": 5.0,
        "invested": 5000.0,
        "clients": 1,
        "entry_date": D("2026-10-05"),
    },
    {
        "symbol": "ZZZ",
        "qty": 1.0,
        "invested": 10.0,
        "clients": 1,
        "entry_date": D("2026-10-02"),
    },
]
CLOSES = [
    _close("AAA", "2026-10-01", 100),
    _close("AAA", "2026-10-05", 110),
    _close("AAA", "2026-10-06", 99),
    _close("BBB", "2026-10-05", 50),
    _close("BBB", "2026-10-06", 50),
    _close("BBB", "2026-10-05", 49, "BSE"),  # fewer bars: must not be mixed in
]


def _build(repo, **kw):
    args = {
        "mode": "day",
        "day": None,
        "start": None,
        "grain": "auto",
        "today": D("2026-10-06"),
    }
    args.update(kw)
    return asyncio.run(HeatmapService(repo).build(None, MID, None, **args))


def test_pick_series_keeps_one_exchange_per_symbol():
    series, used = pick_series(CLOSES)
    assert used["BBB"] == "NSE" and series["BBB"] == [
        ("2026-10-05", 50),
        ("2026-10-06", 50),
    ]


def test_day_mode_defaults_to_latest_close_and_unpriced_is_none():
    out = _build(_Repo(HOLD, CLOSES))
    assert out["day"] == "2026-10-06" and out["latest"] == "2026-10-06"
    t = {x["symbol"]: x for x in out["tiles"]}
    assert math.isclose(t["AAA"]["ret"], -0.10)
    assert t["BBB"]["ret"] == 0.0  # a flat day is 0, a value (R12)
    assert t["ZZZ"]["ret"] is None and out["no_history"] == [
        "ZZZ"
    ]  # no close: None, never 0
    assert [x["symbol"] for x in out["tiles"]][-1] == "ZZZ"  # unknowns sort last


def test_range_mode_starts_at_tracking_day_and_sorts_by_invested():
    out = _build(_Repo(HOLD, CLOSES), mode="range", grain="day")
    assert out["end"] == "2026-10-06" and out["grain"] == "day"
    rows = {r["symbol"]: r for r in out["rows"]}
    assert rows["AAA"]["start"] == "2026-10-01" and math.isclose(
        rows["AAA"]["total"], -0.01
    )
    assert rows["BBB"]["start"] == "2026-10-05" and rows["BBB"]["total"] == 0.0
    assert [r["symbol"] for r in out["rows"]] == ["BBB", "AAA"]


def test_no_holdings_is_empty_not_error():
    out = _build(_Repo([], []))
    assert out["tiles"] == [] and out["rows"] == []


def _hdr(role, manager_id=None):
    token, _ = create_access_token(
        user_id=uuid.uuid4(), role=role, manager_id=manager_id
    )
    return {"Authorization": f"Bearer {token}"}


async def _no_conn():
    yield None


def test_router_authorises_before_reading(monkeypatch):
    repo = _Repo(HOLD, CLOSES)
    monkeypatch.setattr(heatmap_router, "service", HeatmapService(repo))
    app.dependency_overrides[get_db_connection] = _no_conn
    try:
        c = TestClient(app)
        url = f"/api/v1/portfolio/managers/{MID}/heatmap"
        assert c.get(url, headers=_hdr("manager", uuid.uuid4())).status_code == 403
        assert repo.calls == []  # nothing read for a foreign manager
        r = c.get(url, params={"mode": "range"}, headers=_hdr("manager", MID))
        assert r.status_code == 200 and r.json()["mode"] == "range"
        bad = c.get(url, params={"client_ids": "nope"}, headers=_hdr("manager", MID))
        assert bad.status_code == 422
    finally:
        app.dependency_overrides.pop(get_db_connection, None)
