"""Store round-trip, backfill and calendar derivation, exercised end to end against an
in-memory Mongo and a stubbed Angel. No credentials, no database, no network.
"""
import mongomock
import pytest

from app.services.orb import calendar as orb_calendar
from app.services.orb import history, store
from app.services.orb.bars import Bar
from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN
from app.services.orb.universe import Instrument

INST = Instrument(symbol="TESTCO", token="1234", series="EQ", tick=5)


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(store, "get_db", lambda: client["orbtest"])
    store.ensure_indexes()
    yield client


def candle_rows(day, minutes, price=100.0, vol=1000):
    return [[f"{day}T{9 + (555 + m) // 60 - 9:02d}:{(555 + m) % 60:02d}:00+05:30",
             price, price + 1, price - 1, price + 0.5, vol] for m in minutes]


def test_session_round_trip_through_mongo():
    bars = [Bar(minute=MARKET_OPEN + i, o=100 + i, h=110 + i, l=90 + i, c=105 + i, v=7 * i)
            for i in range(10)]
    store.save_session("TESTCO", "2026-09-09", bars, src="rest", last_real=564)
    back = store.load_session("TESTCO", "2026-09-09")
    assert len(back) == 10
    assert [b.minute for b in back] == [b.minute for b in bars]
    assert [b.v for b in back] == [b.v for b in bars]


def test_saving_the_same_session_twice_replaces_rather_than_duplicates():
    bars = [Bar(minute=555, o=1, h=1, l=1, c=1, v=1)]
    store.save_session("TESTCO", "2026-09-09", bars)
    store.save_session("TESTCO", "2026-09-09", bars)
    assert store.get_db()[store.CANDLES_1M].count_documents({"sym": "TESTCO"}) == 1


def test_merge_bars_keeps_what_was_already_written():
    store.merge_bars("TESTCO", "2026-09-09",
                     [Bar(minute=555, o=1, h=1, l=1, c=1, v=10)])
    store.merge_bars("TESTCO", "2026-09-09",
                     [Bar(minute=556, o=2, h=2, l=2, c=2, v=20)])
    got = {b.minute: b.v for b in store.load_session("TESTCO", "2026-09-09")}
    assert got == {555: 10, 556: 20}


def test_merge_overwrites_a_minute_that_was_amended():
    store.merge_bars("TESTCO", "2026-09-09", [Bar(minute=555, o=1, h=1, l=1, c=1, v=10)])
    store.merge_bars("TESTCO", "2026-09-09", [Bar(minute=555, o=1, h=9, l=1, c=9, v=99)])
    bars = store.load_session("TESTCO", "2026-09-09")
    assert len(bars) == 1 and bars[0].c == 9 and bars[0].v == 99


def test_backfill_stores_dense_sessions_and_a_resume_manifest(monkeypatch):
    calls = []

    def fake_candles(token, exch, interval, frm, to):
        calls.append((frm, to))
        return candle_rows("2026-09-09", [0, 1, 5])      # three real minutes

    monkeypatch.setattr(history.angel, "get_candles", fake_candles)
    from datetime import date
    m = history.backfill_minute(INST, date(2026, 9, 1), date(2026, 9, 30))

    bars = store.load_session("TESTCO", "2026-09-09")
    assert len(bars) == MARKET_CLOSE - MARKET_OPEN            # densified to a full session
    assert sum(1 for b in bars if not b.syn) == 3             # only three were real
    doc = store.get(store.CANDLES_1M, "TESTCO:2026-09-09")
    assert doc["real_bars"] == 3 and doc["src"] == "rest"
    assert m["failures"] == 0 and m["days"] == 1
    assert store.get(store.BACKFILL, "TESTCO")["chunks"] == len(calls)


def test_backfill_skips_sessions_already_stored(monkeypatch):
    from datetime import date
    n = {"calls": 0}

    def fake_candles(*a, **k):
        n["calls"] += 1
        return candle_rows("2026-09-09", [0, 1])

    monkeypatch.setattr(history.angel, "get_candles", fake_candles)
    history.backfill_minute(INST, date(2026, 9, 9), date(2026, 9, 9))
    first = n["calls"]
    history.backfill_minute(INST, date(2026, 9, 9), date(2026, 9, 9))
    assert n["calls"] == first, "a stored session must not be re-fetched"


def test_a_failed_chunk_is_counted_not_silently_swallowed(monkeypatch):
    from datetime import date
    monkeypatch.setattr(history.angel, "get_candles", lambda *a, **k: None)
    m = history.backfill_minute(INST, date(2026, 9, 1), date(2026, 9, 5))
    assert m["failures"] == 1 and m["days"] == 0


def test_median_turnover_ranks_liquidity():
    store.save_daily("TESTCO", [{"date": f"2026-08-{d:02d}", "o": 10000, "h": 10100,
                                 "l": 9900, "c": 10000, "v": 1_000_000}
                                for d in range(1, 21)])
    # typical Rs 100 x 1,000,000 shares = Rs 10 cr
    assert round(history.median_turnover_cr("TESTCO"), 1) == 10.0


def test_calendar_is_derived_from_the_data_including_a_weekend_session():
    def sessions(day, real, last_real=929, count=10):
        for i in range(count):
            syn = [False] * real + [True] * (375 - real)
            store.get_db()[store.CANDLES_1M].insert_one(
                {"_id": f"S{i}:{day}", "sym": f"S{i}", "date": day, "n": 375,
                 "syn": syn, "last_real": last_real if real else None})

    sessions("2026-09-09", real=370)                       # ordinary weekday
    sessions("2026-11-08", real=200, last_real=700)        # Sunday muhurat, half day
    sessions("2026-08-15", real=0)                         # holiday: nothing traded

    from datetime import date
    orb_calendar.rebuild(date(2026, 8, 15), date(2026, 8, 15))
    orb_calendar.rebuild(date(2026, 9, 9), date(2026, 9, 9))
    orb_calendar.rebuild(date(2026, 11, 8), date(2026, 11, 8))

    assert orb_calendar.is_trading_day("2026-09-09")
    assert not orb_calendar.is_trading_day("2026-08-15")
    # A Sunday the data says traded is a trading day; the weekday check is not a veto.
    assert orb_calendar.is_trading_day("2026-11-08")
    muhurat = orb_calendar.entry("2026-11-08")
    assert muhurat["weekend"] and muhurat["half_day"]
    assert orb_calendar.session_bounds("2026-11-08") == (MARKET_OPEN, 701, 681)
    assert orb_calendar.session_bounds("2026-09-09") == (MARKET_OPEN, 930, 910)


def test_prior_trading_days_skips_holidays():
    from datetime import date
    for day, real in (("2026-09-07", 370), ("2026-09-08", 370), ("2026-09-09", 0),
                      ("2026-09-10", 370)):
        for i in range(4):
            store.get_db()[store.CANDLES_1M].insert_one(
                {"_id": f"S{i}:{day}", "sym": f"S{i}", "date": day, "n": 375,
                 "syn": [False] * real + [True] * (375 - real), "last_real": 929})
        orb_calendar.rebuild(date.fromisoformat(day), date.fromisoformat(day))
    assert orb_calendar.prior_trading_days("2026-09-10", 3) == ["2026-09-07", "2026-09-08"]
