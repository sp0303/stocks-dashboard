"""A whole synthetic session, driven minute by minute through the real components.

This is the test that would catch a wiring mistake the unit tests cannot: ticks in one
end, a paper trade with the right R out the other, using the same Recorder, Baseline,
PaperBook and strategy the live engine uses. Only the feed and the clock are replaced.
"""
import mongomock
import pytest

from app.services.orb import signals, store
from app.services.orb.config import DEFAULT
from app.services.orb.feed import Tick
from app.services.orb.recorder import Recorder
from app.services.orb.session import ENTRY_FIRST, MARKET_OPEN, OR_END, SQUARE_OFF
from app.services.orb.strategy import LONG

DAY = "2026-09-09"
SYM = "TESTCO"


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    client = mongomock.MongoClient()
    monkeypatch.setattr(store, "get_db", lambda: client["orbtest"])
    yield client


def baseline(**kw):
    b = signals.Baseline(symbol=SYM, token="1234", tick=5, sector_index="NIFTY IT",
                         atr14=400.0, median_or_vol=120_000.0, prev_close=9910,
                         pdh=10500, pdl=9700, median_turnover_cr=150.0,
                         median_daily_vol=5_000_000)
    # Ten prior sessions that had traded 200,000 shares by 09:35.
    b.cum_curves = [{m: 10_000 * (m - MARKET_OPEN + 1) for m in range(MARKET_OPEN, 700)}
                    for _ in range(10)]
    for k, v in kw.items():
        setattr(b, k, v)
    return b


class Driver:
    """Feeds ticks through the recorder exactly as the websocket would, but with the
    minute supplied instead of read from a clock."""

    def __init__(self):
        self.rec = Recorder()
        self.rec.day = DAY
        self.st = self.rec.register(SYM, "1234")
        self.nifty = self.rec.register("NIFTY 50", "99926000")
        self.cum = 0

    def tick(self, minute, price, volume):
        self.cum += volume
        self.st.builder.on_tick(minute, price, self.cum)
        self.st.last_price = price
        self.st.prev_close = 9910
        self.st.ticks += 1

    def index(self, pct):
        self.nifty.prev_close, self.nifty.last_price = 100_000, int(100_000 * (1 + pct / 100))
        self.nifty.ticks += 1

    def close_through(self, minute):
        self.st.builder.roll_to(minute)
        self.st.builder.take_dirty()


def breakout(d, vol=30_000):
    for i in range(5):
        d.tick(OR_END + i, 10150 + i * 10, vol)
    d.close_through(ENTRY_FIRST)


def run_session(breakout_price=10200, breakout_vol=30_000):
    d = Driver()
    d.index(0.5)
    # 09:15-09:30: a 200-paise range on 300,000 shares -> RVOL 2.5, turnover Rs 3 cr.
    for i in range(15):
        m = MARKET_OPEN + i
        d.tick(m, 10100 if i in (3, 7) else 10000, 20_000)
        d.tick(m, 9900 if i in (4, 8) else 10000, 0)
    d.close_through(OR_END)
    return d


def test_a_full_session_produces_one_paper_trade_with_the_expected_risk():
    d = run_session()
    base = {SYM: baseline()}
    screen_doc = signals.run_screen(DAY, d.rec, base, DEFAULT)
    assert SYM in screen_doc["shortlist"], screen_doc["rows"][0]["failed"]

    # 09:30-09:35: breaks out on heavy volume and closes at the high of the bar.
    breakout(d)

    book = signals.PaperBook(DAY, DEFAULT)
    fired = signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book, DEFAULT)
    assert len(fired) == 1 and fired[0]["side"] == LONG

    pos = book.open[SYM]
    assert pos.plan.entry > 10190                      # filled with slippage, not at the close
    assert pos.plan.stop < pos.plan.entry
    assert pos.plan.t1 == pos.plan.entry + int(round(1.5 * pos.plan.risk))
    assert pos.plan.t2 == pos.plan.entry + 200         # range extension

    entry_doc = store.find(store.SIGNALS, {"kind": "entry"})[0]
    assert entry_doc["sym"] == SYM and entry_doc["trace"], "the trace must be persisted"


def test_hitting_t1_books_half_and_moves_the_stop_to_cost():
    d = run_session()
    base = {SYM: baseline()}
    signals.run_screen(DAY, d.rec, base, DEFAULT)
    breakout(d)
    book = signals.PaperBook(DAY, DEFAULT)
    signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book, DEFAULT)
    pos = book.open[SYM]
    entry, qty = pos.plan.entry, pos.plan.qty

    d.tick(ENTRY_FIRST, pos.plan.t1 + 10, 10_000)
    d.close_through(ENTRY_FIRST + 5)
    events = signals.run_manage(DAY, ENTRY_FIRST + 5, d.rec, base, book, DEFAULT)

    assert events and events[0]["event"] == "T1"
    assert SYM in book.open, "half the position keeps running"
    assert book.open[SYM].t1_done and book.open[SYM].stop == entry
    assert book.open[SYM].qty_open == qty - int(qty * 0.5)
    assert book.day_r > 0


def test_square_off_closes_everything_and_is_journalled():
    d = run_session()
    base = {SYM: baseline()}
    signals.run_screen(DAY, d.rec, base, DEFAULT)
    breakout(d)
    book = signals.PaperBook(DAY, DEFAULT)
    signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book, DEFAULT)

    d.tick(SQUARE_OFF - 1, 10250, 5_000)
    signals.square_off(DAY, SQUARE_OFF, d.rec, book)
    assert not book.open
    summary = signals.day_summary(DAY)
    assert summary["trades"] == 1 and summary["by_reason"] == {"SQUARE_OFF": 1}


def test_a_rejected_candidate_records_the_rule_that_stopped_it():
    d = run_session()
    base = {SYM: baseline(median_or_vol=10_000_000.0)}      # RVOL now far below 2x
    doc = signals.run_screen(DAY, d.rec, base, DEFAULT)
    row = doc["rows"][0]
    assert row["passed"] is False and row["failed"] == "C1"
    assert any(c["rule"] == "C1" and not c["ok"] for c in row["trace"])
    assert doc["shortlist"] == []


def test_the_market_alignment_gate_blocks_a_long_into_a_falling_index():
    d = run_session()
    d.index(-0.6)
    base = {SYM: baseline()}
    signals.run_screen(DAY, d.rec, base, DEFAULT)
    breakout(d)
    book = signals.PaperBook(DAY, DEFAULT)
    assert signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book, DEFAULT) == []
    assert not book.open


def test_vwap_that_disagrees_with_the_exchange_suspends_trading():
    """Gate D7. VWAP gates every trade, so a VWAP we cannot trust is a reason to stop,
    not to carry on with a number that is quietly wrong."""
    d = run_session()
    base = {SYM: baseline()}
    signals.run_screen(DAY, d.rec, base, DEFAULT)
    breakout(d)
    book = signals.PaperBook(DAY, DEFAULT)

    d.st.feed_vwap = 10054                       # what we compute: agreement
    assert signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book, DEFAULT)

    book2 = signals.PaperBook(DAY, DEFAULT)
    d.st.feed_vwap = 10800                       # 700bp adrift
    assert signals.run_decide(DAY, ENTRY_FIRST, d.rec, base, [SYM], book2, DEFAULT) == []
