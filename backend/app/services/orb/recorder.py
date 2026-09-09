"""Stage 1 of Segment B: record, and nothing else.

Ticks arrive on the feed's thread and land in per-symbol bar builders held in memory.
Once a minute the recorder flushes completed bars to Mongo. No strategy runs here, no
signal is produced — this ships alone and has to earn five clean sessions before
anything is allowed to trade on what it writes.

The live-vs-truth split is deliberate: the websocket is fast and occasionally wrong (a
reconnect loses ticks and produces a bar that is *incorrect* rather than missing, which
is worse because nothing flags it), while Angel's own candles are slow and
authoritative. recon.py reconciles the two after the close and scores the agreement.
That score is the number that says whether the live engine can be trusted yet.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field

from app.services.orb import store
from app.services.orb.bars import BarBuilder
from app.services.orb.feed import Tick
from app.services.orb.session import (MARKET_CLOSE, MARKET_OPEN, minute_from_epoch_ms,
                                      now_ist, today_ist)

log = logging.getLogger("orb.recorder")


@dataclass
class SymbolState:
    """Per-symbol live state, updated on the feed thread and read by the strategy."""
    symbol: str
    token: str
    builder: BarBuilder
    last_price: int | None = None
    cum_volume: int | None = None
    feed_vwap: int | None = None          # average_traded_price
    prev_close: int | None = None
    day_open: int | None = None
    upper_circuit: int | None = None
    lower_circuit: int | None = None
    ticks: int = 0

    def circuit_distance_pct(self) -> float | None:
        """Distance to the nearer circuit, as a percentage. Equity-only means some names
        carry a 5% or 10% band, and a stock that locks with your stop unfilled turns a
        0.75%-risk trade into an unbounded one."""
        if self.last_price is None:
            return None
        gaps = [abs(lim - self.last_price) / self.last_price * 100.0
                for lim in (self.upper_circuit, self.lower_circuit) if lim]
        return min(gaps) if gaps else None


class Recorder:
    def __init__(self, session_end: int = MARKET_CLOSE):
        self.day = today_ist().isoformat()
        self.session_end = session_end
        self.by_token: dict[str, SymbolState] = {}
        self.by_symbol: dict[str, SymbolState] = {}
        self._lock = threading.Lock()
        self.flushed_bars = 0
        self.dropped_unknown_token = 0

    # ── setup ─────────────────────────────────────────────────────
    def register(self, symbol: str, token: str) -> SymbolState:
        st = SymbolState(symbol=symbol, token=str(token),
                         builder=BarBuilder(symbol, MARKET_OPEN, self.session_end))
        with self._lock:
            self.by_token[str(token)] = st
            self.by_symbol[symbol] = st
        return st

    # ── feed thread ───────────────────────────────────────────────
    def on_tick(self, tick: Tick) -> None:
        st = self.by_token.get(tick.token)
        if st is None:
            self.dropped_unknown_token += 1
            return
        minute = minute_from_epoch_ms(tick.exchange_ts_ms) if tick.exchange_ts_ms \
            else _now_minute()
        with self._lock:
            st.builder.on_tick(minute, tick.ltp, tick.cum_volume)
            st.last_price = tick.ltp
            st.ticks += 1
            if tick.cum_volume is not None:
                st.cum_volume = tick.cum_volume
            if tick.avg_price:
                st.feed_vwap = tick.avg_price
            if tick.prev_close:
                st.prev_close = tick.prev_close
            if tick.day_open:
                st.day_open = tick.day_open
            if tick.upper_circuit:
                st.upper_circuit = tick.upper_circuit
            if tick.lower_circuit:
                st.lower_circuit = tick.lower_circuit

    # ── scheduler thread ──────────────────────────────────────────
    def flush(self, minute: int | None = None) -> int:
        """Close bars whose minute has passed and persist them. Called once a minute.

        Writes go through merge_bars so a flush never erases minutes already stored —
        which matters after a restart, when the process rejoins a session that already
        has bars on disk."""
        m = minute if minute is not None else _now_minute()
        written = 0
        with self._lock:
            states = list(self.by_symbol.values())
        for st in states:
            with self._lock:
                st.builder.roll_to(m)
                dirty = st.builder.take_dirty()
            if not dirty:
                continue
            try:
                store.merge_bars(st.symbol, self.day, dirty, src="ws")
                written += len(dirty)
            except Exception:
                log.exception("failed to persist %s bars — they stay pending", st.symbol)
                with self._lock:
                    for b in dirty:               # put them back for the next flush
                        st.builder._pending.setdefault(b.minute, b)
        self.flushed_bars += written
        return written

    def finalize(self) -> int:
        with self._lock:
            for st in self.by_symbol.values():
                st.builder.finalize()
        return self.flush(self.session_end)

    # ── health ────────────────────────────────────────────────────
    def stats(self) -> dict:
        with self._lock:
            states = list(self.by_symbol.values())
        live = sum(1 for s in states if s.ticks > 0)
        return {
            "date": self.day, "symbols": len(states), "symbols_with_ticks": live,
            "ticks": sum(s.ticks for s in states), "bars_written": self.flushed_bars,
            "unknown_token_ticks": self.dropped_unknown_token,
            "quiet_symbols": [s.symbol for s in states if s.ticks == 0][:20],
        }

    def market_is_open(self) -> bool:
        """The runtime probe from the plan: if nothing anywhere has traded by 09:16, the
        session is not happening — an unscheduled closure no published list would have
        carried. Every scheduled job then stands down."""
        with self._lock:
            return any(s.ticks > 0 for s in self.by_symbol.values())


def _now_minute() -> int:
    n = now_ist()
    return n.hour * 60 + n.minute
