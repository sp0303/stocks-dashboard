"""Assemble 1-minute OHLCV bars from Angel websocket ticks.

The one thing that is easy to get wrong here: a QUOTE tick carries
`volume_trade_for_the_day` — the session's *cumulative* volume, not the trade's size.
A bar's volume is therefore a difference between two cumulative readings, and taking
the field at face value produces volume that grows monotonically all day.

Prices are integer paise throughout (the websocket already sends paise), so a
`close > or_high` comparison can never turn on a floating-point artifact.

No I/O and no clock: the caller supplies the minute. That keeps this unit-testable and
lets a future replay driver push historical ticks through the identical code path.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN

# How many closed bars stay amendable. A tick that arrives after its minute rolled over
# (a reconnect flushing its buffer) still belongs in that bar; beyond this window the
# nightly reconciliation is the right place to fix it, not the live path.
AMEND_WINDOW = 3


@dataclass
class Bar:
    minute: int
    o: int
    h: int
    l: int
    c: int
    v: int
    syn: bool = False       # minute had no trades; o=h=l=c carried from the last close
    vol_ok: bool = True     # False when the cumulative baseline was unknown
    ticks: int = 0

    def as_doc(self) -> dict:
        return {"m": self.minute, "o": self.o, "h": self.h, "l": self.l,
                "c": self.c, "v": self.v, "syn": self.syn, "vok": self.vol_ok}


class BarBuilder:
    """One per symbol per session. Feed it ticks; call roll_to() every minute."""

    def __init__(self, symbol: str, session_start: int = MARKET_OPEN,
                 session_end: int = MARKET_CLOSE):
        self.symbol = symbol
        self.session_start = session_start
        self.session_end = session_end
        self.started_mid_session = False
        self._cur: Bar | None = None
        self._cur_cum: int | None = None      # latest cumulative volume seen in _cur
        self._prev_cum: int | None = None     # cumulative volume as of the last closed bar
        self._last_close: int | None = None
        self._next_minute = session_start     # first minute not yet accounted for
        self._emitted: dict[int, Bar] = {}    # recent closed bars, still amendable
        self._pending: dict[int, Bar] = {}    # closed or amended, not yet persisted
        self._session: dict[int, Bar] = {}    # every closed bar of the session

    # ── ingest ────────────────────────────────────────────────────
    def on_tick(self, minute: int, ltp: int, cum_vol: int | None = None) -> None:
        if ltp is None or minute < self.session_start or minute >= self.session_end:
            return

        # A tick for a minute already closed: amend in place while it is still in range.
        if self._cur is not None and minute < self._cur.minute:
            self._amend(minute, ltp)
            return
        if self._cur is None and minute < self._next_minute:
            self._amend(minute, ltp)
            return

        if self._cur is None or minute > self._cur.minute:
            self._open(minute)

        b = self._cur
        assert b is not None
        if b.ticks == 0:
            b.o = b.h = b.l = b.c = ltp
        else:
            b.h = max(b.h, ltp)
            b.l = min(b.l, ltp)
            b.c = ltp
        b.ticks += 1
        if cum_vol is not None:
            self._cur_cum = max(cum_vol, self._cur_cum or 0)

    def _amend(self, minute: int, ltp: int) -> None:
        bar = self._emitted.get(minute)
        if bar is None:
            return
        bar.h = max(bar.h, ltp)
        bar.l = min(bar.l, ltp)
        bar.c = ltp
        bar.ticks += 1
        bar.syn = False
        self._pending[minute] = bar

    # ── bar boundaries ────────────────────────────────────────────
    def _open(self, minute: int) -> None:
        if self._cur is not None:
            self._close_current()
        elif self._last_close is None and minute > self.session_start:
            # Connected after the open. The minutes before the first tick have no data
            # and no volume baseline, so nothing is invented — reconciliation fills them.
            self.started_mid_session = True
            self._next_minute = minute
        self._fill_gap_to(minute)
        self._cur = Bar(minute=minute, o=0, h=0, l=0, c=0, v=0)
        self._cur_cum = None

    def _close_current(self) -> None:
        b = self._cur
        assert b is not None
        baseline = self._prev_cum
        if baseline is None and b.minute == self.session_start:
            baseline = 0          # the exchange's day counter starts at zero
        if self._cur_cum is None or baseline is None:
            b.v, b.vol_ok = 0, False
        else:
            b.v = max(0, self._cur_cum - baseline)
        if self._cur_cum is not None:
            self._prev_cum = self._cur_cum
        self._last_close = b.c
        self._next_minute = b.minute + 1
        self._emit(b)
        self._cur = None

    def _fill_gap_to(self, minute: int) -> None:
        """Emit flat, zero-volume bars for minutes that saw no trades at all."""
        stop = min(minute, self.session_end)
        if self._last_close is None:
            self._next_minute = max(self._next_minute, stop)
            return
        px = self._last_close
        for m in range(self._next_minute, stop):
            self._emit(Bar(minute=m, o=px, h=px, l=px, c=px, v=0, syn=True))
        self._next_minute = max(self._next_minute, stop)

    def _emit(self, bar: Bar) -> None:
        # Three views of the same Bar objects, each with a different lifetime:
        #   _session  every bar of the day — what the strategy reads
        #   _pending  awaiting a write, never pruned behind the caller's back
        #   _emitted  the short amendment window for late packets
        self._session[bar.minute] = bar
        self._pending[bar.minute] = bar
        self._emitted[bar.minute] = bar
        for m in sorted(self._emitted)[:-AMEND_WINDOW]:
            self._emitted.pop(m, None)

    # ── clock + output ────────────────────────────────────────────
    def roll_to(self, minute: int) -> None:
        """Advance the clock with no tick. Closes the open bar once its minute has
        passed and synthesises any quiet minutes since."""
        if self._cur is not None and minute > self._cur.minute:
            self._close_current()
        self._fill_gap_to(minute)

    def finalize(self) -> None:
        """End of session: close what is open and pad to the session end."""
        if self._cur is not None:
            self._close_current()
        self._fill_gap_to(self.session_end)

    def session_bars(self, before_minute: int | None = None) -> list[Bar]:
        """Every closed bar of the session, oldest first. This is what the strategy
        reads: the amendment window is far too short to compute an opening range from,
        and going back to the database on every decision would make job ordering
        load-bearing for correctness."""
        out = [self._session[m] for m in sorted(self._session)
               if before_minute is None or m < before_minute]
        return out

    def take_dirty(self) -> list[Bar]:
        """Bars written or amended since the last call — this is what gets persisted."""
        out = [self._pending[m] for m in sorted(self._pending)]
        self._pending = {}
        return out


def densify(bars: list[Bar], session_start: int = MARKET_OPEN,
            session_end: int = MARKET_CLOSE) -> list[Bar]:
    """Fill minutes that carry no bar, so every stored session has the same shape.

    Angel's REST candles omit minutes with no trades; the live builder synthesises them.
    Storing both dense means a bar count is a meaningful health number, reconciliation
    compares like with like, and the opening range can ask "is this window complete?"
    without a special case for quiet stocks.

    The invented bars are flat at the last real close and carry zero volume — which is
    what actually happened — and are flagged `syn` so nothing downstream mistakes them
    for trading."""
    have = {b.minute: b for b in bars}
    out: list[Bar] = []
    last: int | None = None
    for m in range(session_start, session_end):
        b = have.get(m)
        if b is not None:
            out.append(b)
            last = b.c
        elif last is not None:
            out.append(Bar(minute=m, o=last, h=last, l=last, c=last, v=0, syn=True))
        # Before the first real bar there is no price to carry, so nothing is invented.
    return out
