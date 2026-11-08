"""Report assembly (R9 pools), worker I/O with a fake connection, and the read-only API."""

import asyncio
import json
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pi_core.analytics.client_report import (
    BenchmarkInput,
    DailyRow,
    ReportInputs,
    build_client_report,
)
from pi_core.models import Segment, Side, Trade
from pi_workers import analytics_compute as ac

D0 = date(2025, 1, 6)
DAYS = [D0 + timedelta(i) for i in range(5)]


def _inputs(trades, **kw):
    base = {
        "trades": trades, "actions": [], "calendar": DAYS,
        "price_lookup": lambda s, e, d: {"AAA": 120.0, "BBB": 210.0}.get(s),
        "today": DAYS[-1], "classes": {}, "notes": {}, "manual_trades": [],
        "daily": [DailyRow(d, 1000.0, 1000.0, 100.0, 0.0) for d in DAYS], "benchmarks": [],
    }
    base.update(kw)
    return ReportInputs(**base)


def test_pools_are_separate_r9():
    trades = [
        Trade("1", D0, "AAA", "NSE", Side.BUY, 10, 100), Trade("2", D0 + timedelta(2), "AAA", "NSE", Side.SELL, 10, 120),
        Trade("3", D0, "CCC", "NSE", Side.BUY, 4, 50), Trade("4", D0, "CCC", "NSE", Side.SELL, 4, 55),
        Trade("5", D0, "NIFTYFUT", "NSE", Side.BUY, 50, 20000, segment=Segment.DERIVATIVE),
        Trade("6", D0, "BBB", "NSE", Side.BUY, 5, 200),
    ]
    r = build_client_report(_inputs(trades))
    assert r["trades"]["delivery"]["closed_trades"] == 1 and r["trades"]["delivery"]["total_pnl"] == 200
    assert r["summary"]["intraday"] == {"trades": 1, "wins": 1, "win_rate": 1.0, "net_pnl": 20}
    assert r["summary"]["derivative_trades"] == 1
    # F&O notional is never capital (R9): only BBB (open) + AAA (closed peak) in invested basis.
    inv = r["summary"]["allocation"]["invested"]["stock"]
    assert {b["key"] for b in inv["buckets"]} == {"AAA", "BBB"} and inv["total"] == 2000
    assert [p["symbol"] for p in r["playbook"]["intraday"]] == ["CCC"]
    json.dumps(r)  # JSON-ready, no inf/NaN objects


def test_benchmarks_and_beta_label():
    levels = {d: 100.0 + i for i, d in enumerate(DAYS)}
    r = build_client_report(_inputs([Trade("1", D0, "BBB", "NSE", Side.BUY, 5, 200)],
                                    benchmarks=[BenchmarkInput("^NSEI", "Nifty 50", False, levels)]))
    perf = r["performance"]
    assert perf["dates"][0] == D0.isoformat() and perf["benchmarks"][0]["stale"] is False
    assert perf["portfolio_pnl"] == [0.0] * 5
    assert r["summary"]["beta_benchmark"] == "Nifty 50"


class FakeConn:
    def __init__(self, trades):
        self.trades, self.executed = trades, []

    async def fetch(self, sql, *args):
        if "FROM ledger.trades" in sql:
            return self.trades
        if "FROM market.benchmarks" in sql:
            return [{"benchmark_id": 2, "code": "^CNX100", "label": "Nifty 100", "is_tri": False},
                    {"benchmark_id": 1, "code": "^NSEI", "label": "Nifty 50", "is_tri": False}]
        if "benchmark_values" in sql:
            return [{"benchmark_id": 1, "value_date": d, "value": Decimal(100 + i)} for i, d in enumerate(DAYS)]
        if "eod_prices" in sql:
            return [{"symbol": "AAA", "exchange": "NSE", "price_date": d, "close": 110.0} for d in DAYS]
        if "client_daily" in sql:
            return [{"as_of": d, "market_value": 1100.0, "net_invested": 1000.0, "nav": 100.0, "day_return": 0.0, "unpriced_cost": 0.0} for d in DAYS]
        if "trade_notes" in sql:
            return [{"trade_id": 1, "note": "journal note"}]
        return []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _row(i, side, src="upload", note=None):
    return {"trade_id": i, "trade_date": D0, "symbol": "AAA", "exchange": "NSE", "trade_type": side,
            "quantity": Decimal(10), "price": Decimal(100), "charges": None, "segment": "EQ",
            "extra": "{}", "source": src, "note": note}


def test_worker_upserts_payload_and_lists_manual_trades():
    conn = FakeConn([_row(1, "buy", "manual", "IPO allotment")])
    assert asyncio.run(ac.recompute_client_analytics(conn, uuid.uuid4(), DAYS[-1], set()))
    _sql, args = next(e for e in conn.executed if "ON CONFLICT (client_id)" in e[0])
    payload = json.loads(args[2])
    assert payload["summary"]["manual_trades"][0]["note"] == "IPO allotment"
    assert [b["code"] for b in payload["performance"]["benchmarks"]] == ["^NSEI", "^CNX100"]
    assert payload["performance"]["benchmarks"][1]["stale"] is True  # no values -> alarm
    # closed trades are rebuilt for the manager-book "Closed trades" tab (replace, never append)
    assert any("DELETE FROM portfolio.round_trips" in e[0] for e in conn.executed)


def test_round_trips_rows_are_written_for_closed_sells():
    sell = {**_row(3, "sell"), "trade_date": DAYS[2]}  # later day: a delivery round trip, not intraday (R9)
    conn = FakeConn([_row(1, "buy"), sell])
    asyncio.run(ac.recompute_client_analytics(conn, uuid.uuid4(), DAYS[-1], set()))
    insert = [e for e in conn.executed if "INSERT INTO portfolio.round_trips" in e[0]]
    assert len(insert) == 1
    symbols, buy_dates, sell_dates, _qty, _buy_px, _sell_px, pnl, _days = insert[0][1][1:]
    assert len(symbols) == len(pnl) >= 1 and all(b <= s for b, s in zip(buy_dates, sell_dates))


def test_unpriced_cost_is_not_a_loss_in_the_pnl_series_r6():
    from datetime import date

    from pi_core.analytics.client_report import DailyRow, _performance
    day = date(2026, 1, 5)
    rows = [DailyRow(day, 0.0, 1000.0, 100.0, 0.0, unpriced_cost=1000.0)]  # everything held is unpriced
    assert _performance(rows, [], [])["portfolio_pnl"] == [0.0]


def test_worker_clears_row_when_no_trades_and_safe_wrapper_swallows():
    conn = FakeConn([])
    asyncio.run(ac.recompute_client_analytics(conn, uuid.uuid4(), DAYS[-1], set()))
    assert any("DELETE FROM portfolio.client_analytics" in e[0] for e in conn.executed)
    assert any("DELETE FROM portfolio.round_trips" in e[0] for e in conn.executed)

    class Boom(FakeConn):
        async def fetch(self, sql, *a):
            raise RuntimeError("db down")
    assert asyncio.run(ac.recompute_client_analytics_safe(Boom([]), uuid.uuid4(), D0, set())) is False


def test_notes_prefer_journal_and_skip_derived():
    notes = ac.notes_by_trade([{"trade_id": 1, "note": "derived:x"}, {"trade_id": 2, "note": "ledger"}],
                              [{"trade_id": 2, "note": "journal"}])
    assert notes == {"2": "journal"}


# ---- API (no DB: deps overridden) ----
from pi_api.core.db import get_db_connection
from pi_api.modules.analytics import router as analytics_router
from pi_api.modules.auth.service import create_access_token

MGR, MINE, OTHER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest.fixture()
def api(monkeypatch):
    app = FastAPI()
    app.include_router(analytics_router.router, prefix="/api/v1")

    async def fake_conn():
        yield object()

    async def allow(conn, client_id, role, manager_id, pcid):
        return client_id == MINE

    calls = []

    async def section(conn, client_id, name):
        calls.append(name)
        return {"as_of": D0, "computed_at": "2025-01-10T00:00:00Z", "engine_version": "a1",
                "data": [{"pool": "delivery", "symbol": "AAA", "pnl": 1.5}] if name.startswith("playbook") else {"k": 1}}

    app.dependency_overrides[get_db_connection] = fake_conn
    monkeypatch.setattr(analytics_router.portfolio_service, "validate_client_access", allow)
    monkeypatch.setattr(analytics_router.service.repo, "get_section", section)
    return TestClient(app), calls


def _hdr():
    token, _ = create_access_token(user_id=uuid.uuid4(), role="manager", manager_id=MGR)
    return {"Authorization": f"Bearer {token}"}


def test_api_requires_auth_and_scopes_before_reading(api):
    client, calls = api
    assert client.get(f"/api/v1/analytics/clients/{MINE}/summary").status_code in (401, 403)
    assert client.get(f"/api/v1/analytics/clients/{OTHER}/summary", headers=_hdr()).status_code == 403
    assert calls == []  # authorise BEFORE reading
    r = client.get(f"/api/v1/analytics/clients/{MINE}/summary", headers=_hdr())
    assert r.status_code == 200 and r.json()["data"] == {"k": 1}
    assert client.get(f"/api/v1/analytics/clients/{MINE}/trades?pool=bogus", headers=_hdr()).status_code == 422


def test_api_playbook_export_is_csv(api):
    client, calls = api
    r = client.get(f"/api/v1/analytics/clients/{MINE}/playbook/export", headers=_hdr())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[1].startswith("delivery,AAA")
    assert calls == ["playbook.delivery", "playbook.intraday"]


def test_equal_partial_fills_merge_into_one_round_trip_row():
    """round_trips is keyed (client, symbol, buy_date, sell_date, quantity): two equal sells collide."""
    from pi_core.analytics.client_report import closed_round_trips
    trades = [
        Trade("b1", DAYS[0], "AAA", "NSE", Side.BUY, 4, 100.0),
        Trade("s1", DAYS[2], "AAA", "NSE", Side.SELL, 2, 110.0),
        Trade("s2", DAYS[2], "AAA", "NSE", Side.SELL, 2, 120.0),
    ]
    rows = closed_round_trips(_inputs(trades))
    assert len(rows) == 1
    r = rows[0]
    assert r["quantity"] == 4 and r["sell_price"] == 115.0 and r["buy_price"] == 100.0 and r["pnl"] == 60.0
