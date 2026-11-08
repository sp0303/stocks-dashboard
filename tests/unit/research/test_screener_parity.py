"""Screener parity with v1: sync transforms, normalised rows (R12 decimals), market context,
sector fallback and the stale flag. No database: connections/repos are faked."""

import asyncio
from datetime import date, datetime, timezone

import pytest
from pi_api.modules.market import health
from pi_api.modules.research.screener import market_context, normalise_snapshot
from pi_api.modules.research.service import ResearchService
from pi_workers import v1_sync_screener as sync


def _v1_stock(i, **kw):
    return {"ticker": f"S{i:03d}", "name": f"Stock {i}", "sector": "Pharma" if i % 2 else None,
            "price": 100.0 + i, "d1": 1.5, "w1": -2.0, "m1": 0.0, "y1": 12.0,
            "from_52w_high": -5.0, "rsi": 55.0, "score": 2.0 - i / 100, "rank": i + 1,
            "setup": "Pullback", "plan": {"expected_hold_days": 7, "entry": 101.0},
            "events": [{"kind": "RESULTS", "date": "2026-11-12"},
                       {"kind": "DIVIDEND", "date": "2026-11-14", "amount": 3.5},
                       {"kind": "BOGUS", "date": "2026-11-14"}], **kw}


def _v1_body(n=60, as_of="2026-11-06"):
    return {"data": {
        "generated_at": "2026-11-06T10:55:00+00:00", "data_as_of": as_of, "count": n,
        "stocks": [_v1_stock(i) for i in range(n)], "stale": True,
        "market": {"regime": {"state": "caution", "size_multiplier": 0.5, "reasons": ["breadth < 50%"],
                              "breadth": 0.42, "vix": 14.2},
                   "expiry": {"next_expiry": "2026-11-24", "sessions_to_expiry": 12, "phase": "early",
                              "in_entry_window": False, "calendar": "official NSE"},
                   "regime_basis": "NIFTYBEES trend", "events_window": {"from": as_of, "to": "2026-11-26",
                                                                         "stocks_with_events": 60}},
    }}


# ── sync transforms ──
def test_api_payload_is_lossless_and_tagged():
    as_of, p = sync.payload_from_api(_v1_body(), "t")
    assert as_of == date(2026, 11, 6)
    assert p["source"] == sync.SOURCE_API and p["units"] == "percent" and p["v1_served_stale"] is True
    assert "stale" not in p and len(p["stocks"]) == 60 and p["market"]["regime"]["state"] == "caution"


@pytest.mark.parametrize("body", [{"data": {"warming": True, "stocks": []}},
                                  _v1_body(n=10), _v1_body(as_of=None)])
def test_api_payload_refuses_unfit_screens(body):
    with pytest.raises(sync.SyncRefused):
        sync.payload_from_api(body, "t")


def test_mongo_thin_snapshot_ranked_by_score():
    doc = {"_id": "2026-11-06", "as_of": "2026-11-06",
           "stocks": [{"ticker": f"t{i}", "score": i, "setup": "No setup", "entry": 10.0} for i in range(55)]}
    as_of, p = sync.payload_from_mongo(doc, "t")
    assert as_of == date(2026, 11, 6) and p["source"] == sync.SOURCE_MONGO
    assert p["stocks"][0]["ticker"] == "T54" and p["stocks"][0]["rank"] == 1


def test_clean_json_nan_becomes_null():
    assert sync.clean_json({"a": [float("nan"), 1.0], "b": float("inf")}) == {"a": [None, 1.0], "b": None}


class _TxConn:
    def __init__(self, status="INSERT 0 1"):
        self.status, self.executed = status, []

    def transaction(self):
        conn = self

        class _Tx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, et, e, tb):
                conn.rolled_back = et is not None
                return False
        return _Tx()

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return self.status


def test_write_snapshot_dry_run_rolls_back_and_skips_job_log():
    as_of, p = sync.payload_from_api(_v1_body(), "t")
    conn = _TxConn()
    rep = asyncio.run(sync.write_snapshot(conn, as_of, p, dry_run=True))
    assert rep["written"] and rep["dry_run"] and conn.rolled_back
    assert len(conn.executed) == 1 and "ON CONFLICT (as_of, model)" in conn.executed[0][0]
    assert conn.executed[0][1][1] == "v1_daily"


def test_write_snapshot_unchanged_rerun_is_noop():
    as_of, p = sync.payload_from_api(_v1_body(), "t")
    conn = _TxConn(status="INSERT 0 0")
    rep = asyncio.run(sync.write_snapshot(conn, as_of, p, dry_run=False))
    assert rep["written"] is False and "ops.job_runs" in conn.executed[1][0]


def test_load_source_auto_falls_back_and_reports_both_errors(monkeypatch):
    monkeypatch.setattr(sync, "fetch_api", lambda url: (_ for _ in ()).throw(OSError("down")))
    with pytest.raises(sync.SyncRefused, match="api: OSError.*mongo: MONGODB_URL"):
        sync.load_source("auto", {"V1_SCREENER_URL": "http://x"}, "t")


# ── API normalisation ──
def test_rows_are_decimals_with_events_and_hold():
    _, p = sync.payload_from_api(_v1_body(), "t")
    r = normalise_snapshot(p)[0]
    assert r["d1"] == pytest.approx(0.015) and r["m1"] == 0.0 and r["y1"] == pytest.approx(0.12)
    assert r["typical_hold_days"] == 7 and r["setup"] == "Pullback"
    assert [e["kind"] for e in r["events"]] == ["RESULTS", "DIVIDEND"]
    ctx = market_context(p)
    assert ctx["regime"]["breadth"] == 0.42 and ctx["expiry"]["phase"] == "early"


class _Repo:
    def __init__(self, payload, as_of):
        self.snap = {"as_of": as_of, "model": "v1_daily", "payload": payload}

    async def get_latest_screener_snapshot(self, conn, model):
        return self.snap

    async def get_security_sectors(self, conn, symbols):
        return {s: "Master Sector" for s in symbols}


def _latest(monkeypatch, as_of, now):
    monkeypatch.setattr(health, "now_utc", lambda: now)

    async def no_calendar(conn, start, end):
        return []
    monkeypatch.setattr("pi_api.modules.market.repository.MarketRepository.get_open_days", no_calendar)
    _, p = sync.payload_from_api(_v1_body(as_of=as_of), "t")
    return asyncio.run(ResearchService(_Repo(p, date.fromisoformat(as_of))).get_latest_screener(None, None))


def test_latest_fresh_snapshot_fills_sector_and_carries_context(monkeypatch):
    res = _latest(monkeypatch, "2026-11-06", datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc))
    assert res["data_as_of"] == date(2026, 11, 6) and res["is_stale"] is False
    assert {r["sector"] for r in res["rows"]} == {"Pharma", "Master Sector"}  # no Unclassified
    assert res["market"]["regime"]["state"] == "caution" and res["source"] == "v1_api"


def test_latest_snapshot_two_sessions_old_is_stale(monkeypatch):
    res = _latest(monkeypatch, "2026-09-22", datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc))
    assert res["is_stale"] is True and res["sessions_behind"] > 1
