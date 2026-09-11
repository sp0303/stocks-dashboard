"""Reconciliation. The case that matters is not a missing bar — it is a *wrong* one,
which a reconnect produces and nothing else flags.
"""
import mongomock
import pytest

from app.services.orb import recon, store
from app.services.orb.bars import Bar, densify
from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN
from app.services.orb.universe import Instrument

INST = Instrument(symbol="TESTCO", token="1234", series="EQ", tick=5)


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(store, "get_db", lambda: client["orbtest"])
    yield client


def bars(spec):
    return [Bar(minute=m, o=o, h=h, l=lo, c=c, v=v) for m, o, h, lo, c, v in spec]


def test_identical_sessions_agree_completely():
    b = bars([(555, 100, 110, 90, 105, 10), (556, 105, 115, 100, 110, 20)])
    r = recon.compare(densify(b, 555, 560), densify(b, 555, 560))
    assert r["agree_pct"] == 100.0 and r["compared"] == 2


def test_a_wrong_bar_is_caught_not_just_a_missing_one():
    ours = bars([(555, 100, 110, 90, 105, 10), (556, 105, 115, 100, 108, 20)])
    ref = bars([(555, 100, 110, 90, 105, 10), (556, 105, 115, 100, 110, 20)])
    r = recon.compare(densify(ours, 555, 560), densify(ref, 555, 560))
    assert r["matched"] == 1 and r["agree_pct"] == 50.0
    assert r["diffs"][0]["m"] == 556


def test_a_minute_we_synthesised_but_the_exchange_traded_counts_as_missing():
    ours = densify(bars([(555, 100, 110, 90, 105, 10)]), 555, 560)   # 556 is synthetic
    ref = densify(bars([(555, 100, 110, 90, 105, 10), (556, 1, 1, 1, 1, 5)]), 555, 560)
    r = recon.compare(ours, ref)
    assert r["missing"] == 1
    assert r["diffs"][0]["why"] == "synthetic"


def test_quiet_minutes_are_not_compared_so_they_cannot_flatter_the_score():
    ours = densify(bars([(555, 100, 110, 90, 105, 10)]), 555, 930)
    ref = densify(bars([(555, 100, 110, 90, 105, 10)]), 555, 930)
    r = recon.compare(ours, ref)
    assert r["compared"] == 1, "374 synthesised minutes must not count as agreement"


def test_small_volume_differences_are_tolerated_but_price_differences_are_not():
    ours = bars([(555, 100, 110, 90, 105, 1000)])
    ref = bars([(555, 100, 110, 90, 105, 1005)])
    assert recon.compare(ours, ref)["agree_pct"] == 100.0
    ref2 = bars([(555, 100, 110, 90, 105, 2000)])
    assert recon.compare(ours, ref2)["agree_pct"] == 0.0


def test_reconcile_repairs_the_stored_session_from_angel(monkeypatch):
    store.save_session("TESTCO", "2026-09-09",
                       densify(bars([(555, 100, 110, 90, 999, 10)]), 555, 930), src="ws")

    def fake_fetch(inst, d1, d2):
        return {"2026-09-09": bars([(555, 100, 110, 90, 105, 10)])}

    monkeypatch.setattr(recon, "fetch_minute_window", fake_fetch)
    r = recon.reconcile_symbol(INST, "2026-09-09")
    assert r["agree_pct"] == 0.0 and r["repaired"] is True
    fixed = {b.minute: b for b in store.load_session("TESTCO", "2026-09-09")}
    assert fixed[555].c == 105, "Angel's candles are authoritative"
    doc = store.get(store.CANDLES_1M, "TESTCO:2026-09-09")
    assert doc["src"] == "rest-repaired" and doc["repaired_at"]


def test_a_failed_candle_fetch_is_not_mistaken_for_a_clean_day(monkeypatch):
    monkeypatch.setattr(recon, "fetch_minute_window", lambda *a: None)
    assert recon.reconcile_symbol(INST, "2026-09-09") is None
    monkeypatch.setattr(recon, "fetch_minute_window", lambda *a: None)
    day = recon.reconcile_day([INST], "2026-09-09")
    assert day["agree_pct"] is None and day["failures"]
    assert day["passes_exit_test"] is False


def test_exit_test_requires_five_consecutive_clean_sessions():
    for i, pct in enumerate([99.9, 99.8, 99.6, 99.7, 99.9]):
        store.put(store.HEALTH, {"_id": f"2026-09-0{i + 1}", "date": f"2026-09-0{i + 1}",
                                 "agree_pct": pct})
    assert recon.exit_test()["passed"] is True
    store.put(store.HEALTH, {"_id": "2026-09-06", "date": "2026-09-06", "agree_pct": 97.2})
    assert recon.exit_test()["passed"] is False
