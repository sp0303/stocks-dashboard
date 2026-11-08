"""Board data: manager holdings obey R6 (unpriced is None, never cost) and the batch
latest-close lookup cleans its input. No database: connections and repos are faked."""

import asyncio
import json
import uuid
from datetime import date

from fastapi.testclient import TestClient
from pi_api.core.db import get_db_connection
from pi_api.main import app
from pi_api.modules.market import router as market_router
from pi_api.modules.market.service import MarketService
from pi_api.modules.portfolio.repository import PortfolioRepository

C1, C2 = uuid.uuid4(), uuid.uuid4()


class _FakeConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, *_a, **_k):
        return self.rows


def _row(price, price_date=date(2026, 10, 1)):
    return {
        "security_id": 7, "symbol": "VENUSREM", "exchange": "NSE",
        "quantity": 30.0, "invested": 3000.0, "client_count": 2,
        "current_price": price, "price_as_of": price_date if price is not None else None,
        "clients": json.dumps([
            {"client_id": str(C1), "name": "A", "quantity": 10.0, "invested": 1000.0},
            {"client_id": str(C2), "name": "B", "quantity": 20.0, "invested": 2000.0},
        ]),
    }


def _holdings(rows):
    return asyncio.run(PortfolioRepository.get_manager_aggregated_holdings(_FakeConn(rows), uuid.uuid4()))


def test_unpriced_holding_is_none_not_cost():
    (h,) = _holdings([_row(None)])
    assert h["current_price"] is None
    assert h["market_value"] is None
    assert h["unrealized_pnl"] is None
    assert h["return_pct"] is None
    assert h["invested"] == 3000.0 and h["avg_cost"] == 100.0  # cost is still reported as cost


def test_priced_holding_math_and_client_breakdown():
    (h,) = _holdings([_row(120.0)])
    assert h["market_value"] == 3600.0
    assert h["unrealized_pnl"] == 600.0
    assert abs(h["return_pct"] - 0.2) < 1e-12  # decimal (R12)
    assert h["price_as_of"] == date(2026, 10, 1)
    assert [c["quantity"] for c in h["clients"]] == [10.0, 20.0]


def test_latest_closes_service_cleans_symbols():
    seen = {}

    class Repo:
        async def get_latest_closes(self, conn, symbols, lookback_days=400):
            seen["symbols"] = symbols
            return []

    asyncio.run(MarketService(Repo()).get_latest_closes(None, [" tcs", "TCS", "", "infy ", "NSE:WIPRO"]))
    assert seen["symbols"] == ["INFY", "TCS", "WIPRO"]


def test_latest_closes_endpoint(monkeypatch):
    async def fake(conn, symbols):
        return [{"symbol": "TCS", "exchange": "NSE", "price": 3012.5,
                 "price_date": date(2026, 10, 1), "source": "orb_rollup"}]

    async def _conn():
        yield object()

    app.dependency_overrides[get_db_connection] = _conn
    monkeypatch.setattr(market_router.service, "get_latest_closes", fake)
    try:
        r = TestClient(app).get("/api/v1/market/closes?symbols=TCS,UNPRICED")
        assert r.status_code == 200
        assert r.json() == [{"symbol": "TCS", "exchange": "NSE", "price": 3012.5,
                             "price_date": "2026-10-01", "source": "orb_rollup",
                             "security_symbol": None, "sessions_behind": None, "is_stale": False}]
    finally:
        app.dependency_overrides.pop(get_db_connection, None)


# --- Root cause of "every board card unpriced": the 30-day window + no staleness ---


class _ClosesRepo:
    """Fake repo: a close 40 days old for DIVISLAB (outside the old 30-day window)."""

    def __init__(self, found, open_days):
        self.found, self.open_days, self.calls = found, open_days, []

    async def get_latest_closes(self, conn, symbols, lookback_days=400):
        self.calls.append((symbols, lookback_days))
        return [f for f in self.found if f["symbol"] in symbols]

    async def get_open_days(self, conn, start, end):
        return [d for d in self.open_days if start <= d <= end]


def _weekdays(start, end):
    from datetime import timedelta
    d, out = start, []
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def test_old_close_is_returned_with_as_of_and_flagged_stale(monkeypatch):
    from datetime import datetime, timezone

    from pi_api.modules.market import health
    monkeypatch.setattr(health, "now_utc", lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc))
    old = {"symbol": "DIVISLAB", "exchange": "NSE", "price": 6100.0,
           "price_date": date(2026, 9, 25), "source": "orb_rollup"}
    fresh = {"symbol": "SHILPAMED", "exchange": "NSE", "price": 820.0,
             "price_date": date(2026, 11, 5), "source": "orb_rollup"}
    repo = _ClosesRepo([old, fresh], _weekdays(date(2026, 1, 1), date(2026, 11, 6)))
    rows = asyncio.run(MarketService(repo).get_latest_closes(None, ["divislab", "SHILPAMED-EQ"]))
    assert repo.calls[0][1] >= 365  # no 30-day window any more
    by = {r["symbol"]: r for r in rows}
    assert by["DIVISLAB"]["price"] == 6100.0 and by["DIVISLAB"]["is_stale"] is True
    assert by["DIVISLAB"]["sessions_behind"] > 1
    # requested spelling is echoed back so the UI lookup by entry.symbol hits
    assert by["SHILPAMED-EQ"]["security_symbol"] == "SHILPAMED"
    assert by["SHILPAMED-EQ"]["is_stale"] is False  # 6 Nov before 16:00 IST: 5 Nov is current


def test_unpriced_symbol_is_absent_not_zero(monkeypatch):
    repo = _ClosesRepo([], [])
    assert asyncio.run(MarketService(repo).get_latest_closes(None, ["NOPRICE"])) == []


def test_normalise_symbol_forms():
    from pi_api.modules.market.closes import normalise_symbol
    assert normalise_symbol(" nse:tcs ") == "TCS"
    assert normalise_symbol("TCS.NS") == "TCS"
    assert normalise_symbol("BAJAJ-AUTO") == "BAJAJ-AUTO"  # hyphen in a real symbol is kept
    assert normalise_symbol("M&M-EQ") == "M&M"
