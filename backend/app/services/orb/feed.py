"""Angel SmartWebSocketV2 — the live tick feed, with a supervisor around it.

Facts this is built on, read from the SDK source rather than documentation:

  * QUOTE mode (2) carries last traded price, `volume_trade_for_the_day` (the session's
    *cumulative* volume), `average_traded_price` (the exchange's own session VWAP),
    day open/high/low and `closed_price` (the previous close). That is everything the
    rulebook needs on a per-tick basis.
  * SNAP_QUOTE mode (3) adds upper/lower circuit limits — which matter now that this
    system trades plain equity and no longer inherits the F&O universe's 20% band.
  * Prices arrive as **integers in paise**. The SDK does not divide, and neither do we.
  * 1,000 token subscriptions per session, 3 connections per client code.
  * `max_retry_attempt` defaults to **1**. One retry and the feed is gone while the
    process still looks healthy — which is the failure this module exists to prevent.

The supervisor adds what the SDK does not: a watchdog on tick arrival (a socket that is
open but silent is the dangerous case, not one that errors), bounded reconnect with
resubscribe, and a status block the /orb page can show.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from app.config import settings

log = logging.getLogger("orb.feed")

MODE_LTP, MODE_QUOTE, MODE_SNAP_QUOTE = 1, 2, 3
EXCH_NSE_CM = 1

MAX_TOKENS_PER_SESSION = 1000
SILENCE_LIMIT_S = 90        # no tick from ANY symbol for this long during market hours
RECONNECT_BACKOFF = (2, 5, 10, 20, 30, 60)


@dataclass
class Tick:
    token: str
    ltp: int                 # paise
    cum_volume: int | None   # volume_trade_for_the_day
    avg_price: int | None    # the exchange's session VWAP, in paise
    prev_close: int | None
    exchange_ts_ms: int
    day_open: int | None = None
    day_high: int | None = None
    day_low: int | None = None
    upper_circuit: int | None = None
    lower_circuit: int | None = None


@dataclass
class FeedStatus:
    connected: bool = False
    subscribed: int = 0
    ticks: int = 0
    last_tick_ts: float = 0.0
    reconnects: int = 0
    last_error: str = ""
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        age = (time.time() - self.last_tick_ts) if self.last_tick_ts else None
        return {"connected": self.connected, "subscribed": self.subscribed,
                "ticks": self.ticks, "seconds_since_last_tick": round(age, 1) if age else None,
                "reconnects": self.reconnects, "last_error": self.last_error,
                "uptime_s": round(time.time() - self.started_at)}


def parse_tick(msg: dict) -> Tick | None:
    """Normalise one decoded websocket message. The SDK hands back ints already; this
    only names them and guards the fields that are absent in LTP mode."""
    try:
        return Tick(
            token=str(msg["token"]),
            ltp=int(msg["last_traded_price"]),
            cum_volume=_int(msg.get("volume_trade_for_the_day")),
            avg_price=_int(msg.get("average_traded_price")),
            prev_close=_int(msg.get("closed_price")),
            exchange_ts_ms=int(msg.get("exchange_timestamp") or 0),
            day_open=_int(msg.get("open_price_of_the_day")),
            day_high=_int(msg.get("high_price_of_the_day")),
            day_low=_int(msg.get("low_price_of_the_day")),
            upper_circuit=_int(msg.get("upper_circuit_limit")),
            lower_circuit=_int(msg.get("lower_circuit_limit")),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class Feed:
    """Owns one websocket connection and keeps it alive.

    `on_tick` is called from the socket's own thread. Keep it cheap — it feeds bar
    builders in memory; nothing in that path should touch the database or the network.
    """

    def __init__(self, on_tick: Callable[[Tick], None], mode: int = MODE_QUOTE):
        self.on_tick = on_tick
        self.mode = mode
        self.status = FeedStatus()
        self._tokens: list[str] = []
        self._snap_tokens: set[str] = set()
        self._ws = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ── lifecycle ─────────────────────────────────────────────────
    def start(self, tokens: list[str]) -> None:
        if len(tokens) > MAX_TOKENS_PER_SESSION:
            log.warning("truncating %d tokens to the %d per-session cap",
                        len(tokens), MAX_TOKENS_PER_SESSION)
            tokens = tokens[:MAX_TOKENS_PER_SESSION]
        self._tokens = [str(t) for t in tokens]
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_forever, name="orb-feed",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.close_connection()
                except Exception:
                    pass
        self.status.connected = False

    def _run_forever(self) -> None:
        """Reconnect loop. The SDK has its own retry, but it defaults to a single
        attempt and gives up silently; this outer loop is what actually keeps the feed
        alive across a morning."""
        attempt = 0
        while not self._stop.is_set():
            try:
                self._connect_once()
            except Exception as exc:
                self.status.last_error = str(exc)
                log.warning("feed connection ended: %s", exc)
            self.status.connected = False
            if self._stop.is_set():
                break
            delay = RECONNECT_BACKOFF[min(attempt, len(RECONNECT_BACKOFF) - 1)]
            attempt += 1
            self.status.reconnects += 1
            log.warning("reconnecting in %ds (attempt %d)", delay, attempt)
            if self._stop.wait(delay):
                break

    def _connect_once(self) -> None:
        from SmartApi.smartWebSocketV2 import SmartWebSocketV2

        from app.services import angel

        smart = angel._ensure_session()          # one session owner: see angel.py's AG8001 note
        feed_token = smart.getfeedToken()
        ws = SmartWebSocketV2(
            smart.access_token, settings.angel_api_key, settings.angel_client_id,
            feed_token,
            max_retry_attempt=5, retry_strategy=1, retry_delay=5, retry_duration=30,
        )

        def on_open(_wsapp):
            self.status.connected = True
            self.status.last_error = ""
            self._subscribe(ws)

        def on_data(_wsapp, message):
            tick = parse_tick(message) if isinstance(message, dict) else None
            if tick is None:
                return
            self.status.ticks += 1
            self.status.last_tick_ts = time.time()
            try:
                self.on_tick(tick)
            except Exception:
                log.exception("on_tick handler raised — dropping this tick")

        def on_error(_wsapp, error):
            self.status.last_error = str(error)
            log.warning("feed error: %s", error)

        ws.on_open = on_open
        ws.on_data = on_data
        ws.on_error = on_error
        ws.on_close = lambda *_: log.info("feed closed")
        with self._lock:
            self._ws = ws
        ws.connect()                              # blocks until the socket ends

    # ── subscriptions ─────────────────────────────────────────────
    def _subscribe(self, ws) -> None:
        if self._tokens:
            ws.subscribe("orb", self.mode, [{"exchangeType": EXCH_NSE_CM,
                                             "tokens": self._tokens}])
            self.status.subscribed = len(self._tokens)
            log.info("subscribed %d tokens in mode %d", len(self._tokens), self.mode)
        if self._snap_tokens:
            ws.subscribe("orb-snap", MODE_SNAP_QUOTE,
                         [{"exchangeType": EXCH_NSE_CM,
                           "tokens": sorted(self._snap_tokens)}])

    def upgrade_to_snap_quote(self, tokens: list[str]) -> None:
        """Move the shortlist to SNAP_QUOTE so circuit limits arrive with the tick.

        Each mode counts separately against the 1,000-subscription cap, which a
        shortlist of eight never threatens."""
        self._snap_tokens.update(str(t) for t in tokens)
        with self._lock:
            ws = self._ws
        if ws is not None and self.status.connected:
            try:
                ws.subscribe("orb-snap", MODE_SNAP_QUOTE,
                             [{"exchangeType": EXCH_NSE_CM,
                               "tokens": sorted(self._snap_tokens)}])
            except Exception as exc:
                log.warning("snap-quote subscribe failed: %s", exc)

    # ── health ────────────────────────────────────────────────────
    def is_silent(self, limit_s: int = SILENCE_LIMIT_S) -> bool:
        """An open socket that has stopped delivering is the dangerous failure: nothing
        errors, the process looks fine, and the bars quietly stop."""
        if not self.status.last_tick_ts:
            return self.status.connected
        return (time.time() - self.status.last_tick_ts) > limit_s
