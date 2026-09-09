"""Bar builder — the component the whole live engine's correctness rests on.

The cases here are the ones that actually happen on a live feed: quiet minutes, a
reconnect mid-session, late packets, and the cumulative-volume arithmetic that is the
single easiest thing to get wrong.
"""
from app.services.orb.bars import BarBuilder
from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN


def build(ticks, roll_to=None, finalize=False):
    b = BarBuilder("TEST")
    for t in ticks:
        b.on_tick(*t)
    if roll_to is not None:
        b.roll_to(roll_to)
    if finalize:
        b.finalize()
    return b, {x.minute: x for x in b.take_dirty()}


def test_ohlc_within_a_minute():
    _, bars = build([(555, 10000, 100), (555, 10500, 150), (555, 9800, 220), (555, 10100, 300)],
                    roll_to=556)
    b = bars[555]
    assert (b.o, b.h, b.l, b.c) == (10000, 10500, 9800, 10100)
    assert b.ticks == 4 and not b.syn


def test_volume_is_a_difference_not_the_cumulative_field():
    # Cumulative day volume: 300 by the end of 09:15, 500 by the end of 09:16.
    _, bars = build([(555, 10000, 300), (556, 10100, 500)], roll_to=557)
    assert bars[555].v == 300      # first bar baselines off zero
    assert bars[556].v == 200      # not 500
    assert bars[555].vol_ok and bars[556].vol_ok


def test_cumulative_volume_never_goes_backwards():
    _, bars = build([(555, 10000, 500), (555, 10010, 400), (556, 10100, 600)], roll_to=557)
    assert bars[555].v == 500
    assert bars[556].v == 100


def test_quiet_minutes_are_synthesised_flat_and_zero_volume():
    _, bars = build([(555, 10000, 300), (558, 10200, 400)], roll_to=559)
    assert sorted(bars) == [555, 556, 557, 558]
    for m in (556, 557):
        assert bars[m].syn and bars[m].v == 0
        assert bars[m].o == bars[m].h == bars[m].l == bars[m].c == 10000  # carried close
    assert bars[558].v == 100      # spans the quiet minutes, correctly


def test_connecting_mid_session_marks_the_first_bar_volume_unusable():
    b = BarBuilder("TEST")
    b.on_tick(600, 10000, 90_000)   # first tick at 10:00; 90,000 already traded today
    b.roll_to(601)
    bars = {x.minute: x for x in b.take_dirty()}
    assert b.started_mid_session
    assert bars[600].vol_ok is False and bars[600].v == 0
    assert 599 not in bars          # nothing invented for the minutes we missed


def test_a_late_tick_amends_its_bar_and_is_re_emitted():
    b = BarBuilder("TEST")
    b.on_tick(555, 10000, 100)
    b.on_tick(556, 10100, 200)
    first = {x.minute: x for x in b.take_dirty()}
    assert first[555].c == 10000
    b.on_tick(555, 10600, 100)      # reconnect flushes a buffered packet
    again = {x.minute: x for x in b.take_dirty()}
    assert 555 in again and again[555].h == 10600 and again[555].c == 10600


def test_take_dirty_never_drops_a_bar_even_across_a_long_gap():
    b = BarBuilder("TEST")
    b.on_tick(555, 10000, 100)
    b.roll_to(575)                  # twenty quiet minutes, far beyond the amend window
    got = b.take_dirty()
    assert [x.minute for x in got] == list(range(555, 575))


def test_ticks_outside_the_session_are_ignored():
    b = BarBuilder("TEST")
    b.on_tick(MARKET_OPEN - 1, 10000, 10)
    b.on_tick(MARKET_CLOSE, 10000, 10)
    assert b.take_dirty() == []


def test_finalize_pads_to_the_close():
    b = BarBuilder("TEST")
    b.on_tick(555, 10000, 100)
    b.finalize()
    bars = b.take_dirty()
    assert [x.minute for x in bars] == list(range(MARKET_OPEN, MARKET_CLOSE))
    assert len(bars) == 375
    assert all(x.syn for x in bars[1:])


def test_take_dirty_is_idempotent():
    b, _ = build([(555, 10000, 100)], roll_to=556)
    assert b.take_dirty() == []
