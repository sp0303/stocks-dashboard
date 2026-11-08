"""v1 orb_* document -> orb.* row mapping (pure)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from pi_workers import orb_feed as f

from tests.unit.orb import fixtures as fx


def test_universe_maps_typed_columns_and_keeps_json():
    row = f.map_universe(fx.universe_doc())
    assert row["legacy_id"] == "2026-10-01"
    assert row["trade_date"] == date(2026, 10, 1)
    assert row["size"] == 2
    assert row["min_turnover_cr"] == Decimal("25.5")
    assert json.loads(row["members"])[0]["sym"] == "AAA"
    assert json.loads(row["pool"]) == 1800
    assert json.loads(row["extra"]) == {}
    assert row["source"] == "v1_mongo"


def test_screen_signal_keeps_rows_and_sanitises_nan():
    row = f.map_signal(fx.screen_doc())
    assert row["kind"] == "screen"
    assert row["candidates"] == 2 and row["passed"] == 1
    rows = json.loads(row["screen_rows"])  # must be valid JSON for jsonb (no NaN)
    assert rows[1]["rvol"] is None
    assert row["at"] == datetime(2026, 10, 1, 4, 1, 2, tzinfo=timezone.utc)


def test_entry_signal_prices_stay_integer_paise():
    row = f.map_signal(fx.entry_doc())
    assert (row["entry_paise"], row["stop_paise"], row["t1_paise"], row["t2_paise"]) == (
        101100, 100400, 102500, 103900)
    assert row["risk_paise"] == 9800 and row["qty"] == 14 and row["side"] == 1
    assert row["sym"] == "AAA" and row["minute"] == 575


def test_health_kinds_and_epoch_timestamp():
    recon, recorder, beat = (f.map_health(d) for d in fx.health_docs())
    assert recon["kind"] == "reconcile" and recon["agree_pct"] == Decimal("99.867")
    assert recon["passes_exit_test"] is True
    assert set(json.loads(recon["extra"])) == {"repaired_symbols", "failures", "worst"}
    assert recorder["kind"] == "recorder"
    assert json.loads(recorder["extra"]) == {"ticks": 5}
    assert beat["kind"] == "heartbeat"
    assert beat["at"].tzinfo is not None and beat["at"].year == 2026
    assert json.loads(beat["extra"])["minute"] == 600


def test_jobs_include_lock_doc_without_date():
    run, lock = (f.map_job(d) for d in fx.job_docs())
    assert run["job"] == "screen" and run["ok"] is True and run["seconds"] == Decimal("1.234")
    assert lock["trade_date"] is None and lock["job"] is None and lock["owner"] == "host:1"
    assert "expires_at" in json.loads(lock["extra"])


def test_journal_objectid_becomes_text_legacy_id():
    row = f.map_journal(fx.journal_doc())
    assert row["legacy_id"] == "65f000000000000000000001"
    assert row["price_paise"] == 102500 and row["r"] == Decimal("0.714")


def test_rejects_documents_without_a_date():
    assert f.map_signal({"_id": "junk", "kind": "screen"}) is None
    assert f.map_journal({"_id": "x", "sym": "AAA"}) is None
    assert f.map_universe({"_id": "nodate"}) is None


def test_hash_is_stable_and_changes_with_content():
    a, b = fx.entry_doc(), fx.entry_doc()
    assert f.map_signal(a)["source_hash"] == f.map_signal(b)["source_hash"]
    b["qty"] = 15
    assert f.map_signal(a)["source_hash"] != f.map_signal(b)["source_hash"]


def test_every_mapper_yields_consistent_columns():
    for spec in f.TABLES:
        docs = fx.all_docs()[spec.collection]
        keys = {tuple(r) for r in (spec.mapper(d) for d in docs) if r is not None}
        assert len(keys) == 1, spec.table
