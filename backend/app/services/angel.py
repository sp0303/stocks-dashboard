"""Angel One SmartAPI integration — live quotes + historical candles.

Chosen over Kite because it logs in **programmatically via TOTP** (no browser
redirect, no public https callback), is free, and includes historical data. A session
is created on first use and re-created when it ages out; TOTP means we can re-auth at
any time without user interaction.

Symbol → token mapping comes from Angel's public "scrip master" JSON (cached daily).
Angel's NSE cash tradingsymbols carry a series suffix (SBIN-EQ, VENUSREM-BE); we key the
map by the bare symbol so callers can keep passing plain tickers.
"""
from __future__ import annotations

import collections
import logging
import threading
import time
from pathlib import Path

from app.config import settings

log = logging.getLogger("angel")

_SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
_SCRIP_CACHE = Path(settings.data_dir) / "angel_scrip_master.json"
_SESSION_MAX_AGE = 6 * 3600  # re-login every 6h (tokens last a day; this is a safe margin)

_lock = threading.Lock()
_smart = None            # SmartConnect instance
_session_ts = 0.0        # when the current session was created


class _RateLimiter:
    """Rate gate shared across threads, enforcing Angel's multi-window limits:
      • per-second  — a minimum interval between calls (paces bursts), and
      • per-minute / per-hour — rolling-window ceilings.
    acquire() sleeps to honour the per-second pace, then returns False if a minute/hour
    ceiling is already hit — callers then skip Angel and fall back to Yahoo rather than
    blocking a request or burning the quota. The concurrent price-matrix fan-out
    serialises here instead of hammering the API."""

    def __init__(self, min_interval: float, per_min: int, per_hour: int):
        self.min_interval = min_interval
        self.per_min = per_min
        self.per_hour = per_hour
        self._lock = threading.Lock()
        self._last = 0.0
        self._calls: "collections.deque[float]" = collections.deque()

    def acquire(self) -> bool:
        with self._lock:
            now = time.time()
            # drop timestamps older than an hour
            while self._calls and now - self._calls[0] > 3600:
                self._calls.popleft()
            in_hour = len(self._calls)
            in_min = sum(1 for t in self._calls if now - t <= 60)
            if in_hour >= self.per_hour or in_min >= self.per_min:
                return False  # over budget — caller should fall back
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                time.sleep(wait)
            now = time.time()
            self._last = now
            self._calls.append(now)
            return True


# Official Angel One SmartAPI limits (per the published rate-limit table):
#   market/v1/quote        -> 10/s, 500/min, 5000/hr
#   historical/getCandleData -> 3/s, 180/min, 5000/hr
# We gate to exactly these. In practice volume is far lower (quotes are 15-min cached and
# batched ≤50/call; candles are 30-min cached), so these ceilings are a safety backstop.
_quote_limiter = _RateLimiter(0.10, per_min=500, per_hour=5000)    # quote: 10/s
_candle_limiter = _RateLimiter(0.34, per_min=180, per_hour=5000)   # candle: ~3/s


def _rate_limited(msg: str) -> bool:
    m = (msg or "").lower()
    return "access rate" in m or "too many" in m or "ab1004" in m


def _call(fn, params, limiter: _RateLimiter, what: str, retries: int = 3):
    """Invoke an Angel API method through the rate-limit gate. Returns None when the
    minute/hour budget is exhausted (caller falls back to Yahoo) or all retries fail;
    retries with exponential backoff when Angel reports the access rate was exceeded."""
    for attempt in range(retries):
        if not limiter.acquire():
            log.warning("angel %s over minute/hour budget — falling back", what)
            return None
        try:
            resp = fn(params)
        except Exception as exc:
            if attempt == retries - 1:
                raise
            log.warning("angel %s exception (retry %d): %s", what, attempt + 1, exc)
            time.sleep(2 ** attempt)
            continue
        if isinstance(resp, dict) and not resp.get("status") and _rate_limited(str(resp.get("message"))):
            log.warning("angel %s rate-limited (retry %d)", what, attempt + 1)
            time.sleep(2 ** attempt)
            continue
        return resp
    return None
_nse: dict[str, str] = {}   # bare symbol -> token (NSE cash)
_bse: dict[str, str] = {}   # bare symbol -> token (BSE cash)
_maps_loaded = False


def is_enabled() -> bool:
    return settings.angel_enabled


# ── symbol/token master ────────────────────────────────────────────
def _load_scrip_master(force: bool = False) -> None:
    global _nse, _bse, _maps_loaded
    if _maps_loaded and not force:
        return
    data = None
    try:
        if _SCRIP_CACHE.exists() and (time.time() - _SCRIP_CACHE.stat().st_mtime) < 86400:
            import json
            data = json.loads(_SCRIP_CACHE.read_text())
    except Exception:
        data = None
    if data is None:
        import httpx
        r = httpx.get(_SCRIP_URL, timeout=60.0)
        r.raise_for_status()
        data = r.json()
        try:
            _SCRIP_CACHE.parent.mkdir(parents=True, exist_ok=True)
            _SCRIP_CACHE.write_text(r.text)
        except Exception as exc:
            log.warning("could not cache scrip master: %s", exc)

    nse: dict[str, str] = {}
    bse: dict[str, str] = {}
    for row in data:
        seg = row.get("exch_seg")
        sym = row.get("symbol") or ""
        tok = row.get("token")
        if not tok:
            continue
        if seg == "NSE" and (sym.endswith("-EQ") or sym.endswith("-BE")):
            base = sym.rsplit("-", 1)[0]
            # prefer the -EQ listing over -BE if both exist
            if base not in nse or sym.endswith("-EQ"):
                nse[base] = tok
        elif seg == "BSE":
            # BSE cash rows: name is the plain ticker; keep first seen
            name = (row.get("name") or sym)
            if name and name not in bse:
                bse[name] = tok
    _nse, _bse, _maps_loaded = nse, bse, True
    log.info("angel scrip master: %d NSE, %d BSE symbols", len(nse), len(bse))


def _token_for(symbol: str, exchange: str) -> tuple[str, str] | None:
    """Return (exchange, token) for a symbol, trying the given exchange then the other."""
    _load_scrip_master()
    ex = (exchange or "NSE").upper()
    order = ("NSE", "BSE") if ex == "NSE" else ("BSE", "NSE")
    for e in order:
        tok = (_nse if e == "NSE" else _bse).get(symbol)
        if tok:
            return e, tok
    return None


# ── session ────────────────────────────────────────────────────────
def _ensure_session():
    """Return a logged-in SmartConnect, (re)creating the session if missing/stale."""
    global _smart, _session_ts
    with _lock:
        if _smart is not None and (time.time() - _session_ts) < _SESSION_MAX_AGE:
            return _smart
        import pyotp
        from SmartApi import SmartConnect

        smart = SmartConnect(api_key=settings.angel_api_key)
        totp = pyotp.TOTP(settings.angel_totp_secret).now()
        resp = smart.generateSession(settings.angel_client_id, settings.angel_pin, totp)
        if not resp.get("status"):
            raise RuntimeError(f"Angel login failed: {resp.get('message')}")
        _smart, _session_ts = smart, time.time()
        log.info("angel session established")
        return _smart


def is_ready() -> bool:
    if not is_enabled():
        return False
    try:
        _ensure_session()
        return True
    except Exception as exc:
        log.warning("angel not ready: %s", exc)
        return False


def status() -> dict:
    ok = False
    err = None
    if is_enabled():
        try:
            _ensure_session()
            ok = True
        except Exception as exc:
            err = str(exc)
    return {"enabled": is_enabled(), "authenticated": ok, "error": err}


# ── quotes ─────────────────────────────────────────────────────────
def _market_data(mode: str, symbols: list[str], exchanges: dict[str, str]) -> dict[str, dict]:
    """Call getMarketData for the given symbols and return {our_symbol: fetched_row}.
    Groups tokens by exchange and batches to Angel's 50-instrument limit."""
    smart = _ensure_session()
    # resolve tokens; keep reverse maps to translate the response back to our symbols
    by_exchange: dict[str, list[str]] = {"NSE": [], "BSE": []}
    tok_to_sym: dict[tuple[str, str], str] = {}
    for s in symbols:
        r = _token_for(s, exchanges.get(s, "NSE"))
        if not r:
            continue
        ex, tok = r
        by_exchange[ex].append(tok)
        tok_to_sym[(ex, tok)] = s

    out: dict[str, dict] = {}
    # batch across a flat list but keep exchange grouping per request
    for ex, toks in by_exchange.items():
        for i in range(0, len(toks), 50):
            batch = toks[i : i + 50]
            if not batch:
                continue
            try:
                resp = _call(lambda p: smart.getMarketData(p[0], p[1]), (mode, {ex: batch}),
                             _quote_limiter, "getMarketData")
            except Exception as exc:
                log.warning("angel getMarketData error: %s", exc)
                continue
            if not resp:  # over budget or failed — leave these for the fallback
                continue
            if not resp.get("status"):
                log.warning("angel getMarketData: %s", resp.get("message"))
                continue
            for row in resp.get("data", {}).get("fetched", []):
                key = (row.get("exchange"), str(row.get("symbolToken")))
                sym = tok_to_sym.get(key)
                if sym:
                    out[sym] = row
    return out


def quote_details(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """Per-symbol {price, prev_close, change, change_pct, day_high, day_low, volume}."""
    if not symbols or not is_ready():
        return {}
    try:
        rows = _market_data("FULL", symbols, exchanges or {})
    except Exception as exc:
        log.warning("angel quote_details failed: %s", exc)
        return {}
    out: dict[str, dict] = {}
    for s, row in rows.items():
        price = row.get("ltp")
        prev = row.get("close")  # previous trading day's close
        if price is None:
            continue
        change = round(price - prev, 2) if prev is not None else None
        change_pct = round(change / prev * 100, 2) if (change is not None and prev) else None
        out[s] = {
            "price": round(price, 2),
            "prev_close": round(prev, 2) if prev is not None else None,
            "change": change,
            "change_pct": change_pct,
            "volume": row.get("tradeVolume"),
            "day_high": round(row["high"], 2) if row.get("high") is not None else None,
            "day_low": round(row["low"], 2) if row.get("low") is not None else None,
        }
    return out


def get_quotes(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, float]:
    """{symbol: last_price} — LTP mode is lighter than FULL."""
    if not symbols or not is_ready():
        return {}
    try:
        rows = _market_data("LTP", symbols, exchanges or {})
    except Exception as exc:
        log.warning("angel get_quotes failed: %s", exc)
        return {}
    return {s: round(r["ltp"], 2) for s, r in rows.items() if r.get("ltp") is not None}


# ── historical ─────────────────────────────────────────────────────
_INTERVAL = {"1d": "ONE_DAY", "1wk": "ONE_DAY", "1mo": "ONE_DAY"}  # Angel has no wk/mo; use daily


def get_history(symbol: str, from_date: str | None = None, interval: str = "1d",
                exchange: str = "NSE") -> list[dict] | None:
    """Daily close history as [{date, close}] from Angel candles, or None on failure
    (caller falls back to Yahoo). from_date is 'YYYY-MM-DD'."""
    if not is_ready():
        return None
    r = _token_for(symbol, exchange)
    if not r:
        return None
    ex, tok = r
    from datetime import date, datetime, timedelta

    start = from_date or (date.today() - timedelta(days=365)).isoformat()
    params = {
        "exchange": ex,
        "symboltoken": tok,
        "interval": _INTERVAL.get(interval, "ONE_DAY"),
        "fromdate": f"{start} 09:15",
        "todate": f"{date.today().isoformat()} 15:30",
    }
    try:
        smart = _ensure_session()
        resp = _call(smart.getCandleData, params, _candle_limiter, "getCandleData")
    except Exception as exc:
        log.warning("angel getCandleData error for %s: %s", symbol, exc)
        return None
    if not resp or not resp.get("status") or not resp.get("data"):
        return None
    points = []
    for c in resp["data"]:
        # c = [timestamp, open, high, low, close, volume]
        try:
            d = datetime.fromisoformat(c[0]).strftime("%Y-%m-%d")
        except Exception:
            d = str(c[0])[:10]
        points.append({"date": d, "close": round(float(c[4]), 2)})
    return points
