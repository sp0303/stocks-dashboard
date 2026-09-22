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
import itertools
import logging
import threading
import time
from pathlib import Path

from app.config import settings

log = logging.getLogger("angel")

_SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
_SCRIP_CACHE = Path(settings.data_dir) / "angel_scrip_master.json"
_SESSION_MAX_AGE = 6 * 3600  # re-login every 6h (tokens last a day; this is a safe margin)

# Sentinel returned by a single account when it is over budget / rate-limited / unusable,
# so the pool knows to try the next account rather than treating it as a real response.
_OVER_BUDGET = object()


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
# We gate each account to exactly these — every account carries the full budget, so two
# accounts roughly double the effective ceiling. In practice volume is far lower (quotes
# are 15-min cached and batched ≤50/call; candles 30-min cached), so these are a backstop.
class _Account:
    """One Angel login: its own session, and its own rate limiters. Keeping the limiters
    per-account is the whole point — the pool spreads load and fails over between accounts
    that each have their own independent quota."""

    def __init__(self, name: str, api_key: str, client_id: str, pin: str, totp_secret: str):
        self.name = name
        self.api_key = api_key
        self.client_id = client_id
        self.pin = pin
        self.totp_secret = totp_secret
        self.lock = threading.Lock()
        self.smart = None
        self.session_ts = 0.0
        self.quote_limiter = _RateLimiter(0.10, per_min=500, per_hour=5000)    # quote: 10/s
        self.candle_limiter = _RateLimiter(0.34, per_min=180, per_hour=5000)   # candle: ~3/s


def _build_accounts() -> list["_Account"]:
    accts: list[_Account] = []
    if settings.angel_enabled:
        accts.append(_Account("primary", settings.angel_api_key, settings.angel_client_id,
                              settings.angel_pin, settings.angel_totp_secret))
    if settings.angel2_enabled:
        accts.append(_Account("secondary", settings.angel2_api_key, settings.angel2_client_id,
                              settings.angel2_pin, settings.angel2_totp_secret))
    return accts


_ACCOUNTS: list[_Account] = _build_accounts()
_rr = itertools.count()  # round-robin cursor: spreads calls across accounts


def _rate_limited(msg: str) -> bool:
    m = (msg or "").lower()
    return "access rate" in m or "too many" in m or "ab1004" in m


def _is_auth_error(resp) -> bool:
    """AG8001/AG8002 'Invalid Token' — the session's auth token was rejected: it
    expired, or (commonly) the same Angel login was used by another process, which
    invalidates this one's token. Signals that we should re-authenticate."""
    if not isinstance(resp, dict):
        return False
    code = str(resp.get("errorCode") or "").upper()
    msg = str(resp.get("message") or "").lower()
    return code in ("AG8001", "AG8002", "AG8003") or "invalid token" in msg or "invalid session" in msg


def _invalidate_session(acct: "_Account") -> None:
    """Drop this account's cached session so its next use logs in fresh."""
    with acct.lock:
        acct.smart, acct.session_ts = None, 0.0


def _call(fn, params, kind: str, what: str):
    """Invoke an Angel method through the account pool. `fn` is called as fn(smart, params);
    `kind` is "quote" or "candle" and selects which per-account limiter gates the call.

    The starting account is round-robined so load spreads across accounts; then it fails
    over — an account that is over budget, rate-limited, or unusable is skipped and the next
    is tried. Returns None only when every account is exhausted (caller falls back to Yahoo).
    """
    if not _ACCOUNTS:
        return None
    n = len(_ACCOUNTS)
    start = next(_rr) % n
    for off in range(n):
        acct = _ACCOUNTS[(start + off) % n]
        resp = _call_account(acct, fn, params, kind, what)
        if resp is not _OVER_BUDGET:
            return resp
    log.warning("angel %s: all accounts over budget/unavailable — falling back", what)
    return None


def _call_account(acct: "_Account", fn, params, kind: str, what: str):
    """Run one call on one account. Returns the response, or the _OVER_BUDGET sentinel to
    tell the pool to move on to the next account. Self-heals an expired/invalidated token
    once in place (the daily reset, or a token invalidated by a login elsewhere)."""
    limiter = acct.quote_limiter if kind == "quote" else acct.candle_limiter
    for attempt in range(2):  # a second pass only to re-auth after an auth error
        if not limiter.acquire():
            log.warning("angel %s over minute/hour budget [%s] — trying next account", what, acct.name)
            return _OVER_BUDGET
        try:
            smart = _ensure_session(acct)
        except Exception as exc:
            log.warning("angel %s login failed [%s]: %s — trying next account", what, acct.name, exc)
            return _OVER_BUDGET
        try:
            resp = fn(smart, params)
        except Exception as exc:
            # A blown quota can arrive as a non-JSON body the SDK fails to parse — i.e. an
            # exception. Retrying can't beat a time-based budget; hand off to the next account.
            if _rate_limited(str(exc)):
                log.warning("angel %s rate-limited [%s] — trying next account", what, acct.name)
            else:
                log.warning("angel %s exception [%s]: %s — trying next account", what, acct.name, exc)
            return _OVER_BUDGET
        if isinstance(resp, dict) and not resp.get("status"):
            if _rate_limited(str(resp.get("message"))):
                log.warning("angel %s rate-limited [%s] — trying next account", what, acct.name)
                return _OVER_BUDGET
            if _is_auth_error(resp) and attempt == 0:
                log.warning("angel %s auth error [%s] — re-authenticating and retrying", what, acct.name)
                _invalidate_session(acct)
                continue
        return resp
    return _OVER_BUDGET
_nse: dict[str, str] = {}   # bare symbol -> token (NSE cash)
_bse: dict[str, str] = {}   # bare symbol -> token (BSE cash)
_maps_loaded = False


def is_enabled() -> bool:
    return bool(_ACCOUNTS)


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
def _ensure_session(acct: "_Account | None" = None):
    """Return a logged-in SmartConnect for `acct`, (re)creating it if missing/stale.
    Defaults to the primary account — single-account callers and the ORB feed use it."""
    acct = acct or (_ACCOUNTS[0] if _ACCOUNTS else None)
    if acct is None:
        raise RuntimeError("Angel is not configured")
    with acct.lock:
        if acct.smart is not None and (time.time() - acct.session_ts) < _SESSION_MAX_AGE:
            return acct.smart
        import pyotp
        from SmartApi import SmartConnect

        smart = SmartConnect(api_key=acct.api_key)
        totp = pyotp.TOTP(acct.totp_secret).now()
        resp = smart.generateSession(acct.client_id, acct.pin, totp)
        if not resp.get("status"):
            raise RuntimeError(f"Angel login failed [{acct.name}]: {resp.get('message')}")
        acct.smart, acct.session_ts = smart, time.time()
        log.info("angel session established [%s]", acct.name)
        return acct.smart


def is_ready() -> bool:
    """True if at least one configured account can authenticate."""
    if not is_enabled():
        return False
    for acct in _ACCOUNTS:
        try:
            _ensure_session(acct)
            return True
        except Exception as exc:
            log.warning("angel account [%s] not ready: %s", acct.name, exc)
    return False


def status() -> dict:
    """Per-account auth status, plus the original top-level shape the BrokerPill reads
    (authenticated = any account is logged in)."""
    accounts = []
    any_ok = False
    for acct in _ACCOUNTS:
        ok, err = False, None
        try:
            _ensure_session(acct)
            ok = any_ok = True
        except Exception as exc:
            err = str(exc)
        accounts.append({"name": acct.name, "authenticated": ok, "error": err})
    first_err = next((a["error"] for a in accounts if a["error"]), None)
    return {"enabled": is_enabled(), "authenticated": any_ok, "error": first_err,
            "accounts": accounts}


# ── quotes ─────────────────────────────────────────────────────────
def _market_data(mode: str, symbols: list[str], exchanges: dict[str, str]) -> dict[str, dict]:
    """Call getMarketData for the given symbols and return {our_symbol: fetched_row}.
    Groups tokens by exchange and batches to Angel's 50-instrument limit. The account pool
    (in _call) handles session choice, rate-limit failover and auth self-heal."""
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

    def _fetch(batch, ex):
        return _call(lambda smart, p: smart.getMarketData(p[0], p[1]), (mode, {ex: batch}),
                     "quote", "getMarketData")

    out: dict[str, dict] = {}
    # batch across a flat list but keep exchange grouping per request
    for ex, toks in by_exchange.items():
        for i in range(0, len(toks), 50):
            batch = toks[i : i + 50]
            if not batch:
                continue
            resp = _fetch(batch, ex)
            if not resp:  # every account over budget or failed — leave these for the fallback
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


#: A quote whose last exchange trade is older than this is not a live price. Long enough
#: for the longest Indian market-holiday runs, short enough to catch a frozen feed.
_QUOTE_MAX_AGE_DAYS = 7


def _is_stale_quote(row: dict, now=None, max_age_days: int = _QUOTE_MAX_AGE_DAYS) -> bool:
    """True when a FULL-mode row's last trade time is older than `max_age_days`.

    Angel will happily serve a frozen instrument's last price as the LTP. VENUSREM's NSE
    record stopped updating on 12-Jun-2026 and kept returning Rs 1,797.50 for three months
    while the stock traded near Rs 1,582 — a 13.6% overstatement (Rs 48,658 across the
    book) that surfaced as "inflated" unrealized P&L. A row with no timestamp is accepted:
    absence of the field is not evidence of staleness.
    """
    from datetime import datetime

    raw = row.get("exchTradeTime")
    if not raw:
        return False
    try:
        traded = datetime.strptime(str(raw), "%d-%b-%Y %H:%M:%S")
    except ValueError:
        return False
    return ((now or datetime.now()) - traded).days > max_age_days


def get_quotes(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, float]:
    """{symbol: last_price}, omitting any symbol whose quote is stale.

    Uses FULL mode rather than LTP because only FULL carries the last-trade timestamp; it is
    the same single call per 50-instrument batch. Omitted symbols fall through to the next
    provider in the composite (Yahoo), which is the point.
    """
    if not symbols or not is_ready():
        return {}
    try:
        rows = _market_data("FULL", symbols, exchanges or {})
    except Exception as exc:
        log.warning("angel get_quotes failed: %s", exc)
        return {}
    out: dict[str, float] = {}
    for s, r in rows.items():
        if r.get("ltp") is None:
            continue
        if _is_stale_quote(r):
            log.warning("angel quote for %s is stale (last trade %s) — deferring to fallback",
                        s, r.get("exchTradeTime"))
            continue
        out[s] = round(r["ltp"], 2)
    return out


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
        resp = _call(lambda smart, p: smart.getCandleData(p), params, "candle", "getCandleData")
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


# ── raw candles (used by the ORB engine) ───────────────────────────
# get_history() above returns daily closes for charts. The ORB backfill needs full
# OHLCV at minute resolution, the exchange's own timestamps, and the ability to say
# "this window returned nothing" distinctly from "this call failed" — so it gets its
# own entry point rather than widening get_history()'s contract.
CANDLE_INTERVALS = {
    "1m": "ONE_MINUTE", "3m": "THREE_MINUTE", "5m": "FIVE_MINUTE", "10m": "TEN_MINUTE",
    "15m": "FIFTEEN_MINUTE", "30m": "THIRTY_MINUTE", "1h": "ONE_HOUR", "1d": "ONE_DAY",
}

# Angel caps the span of a single historical request by interval. Callers must chunk.
MAX_DAYS_PER_REQUEST = {
    "ONE_MINUTE": 30, "THREE_MINUTE": 60, "FIVE_MINUTE": 100, "TEN_MINUTE": 100,
    "FIFTEEN_MINUTE": 200, "THIRTY_MINUTE": 200, "ONE_HOUR": 400, "ONE_DAY": 2000,
}


def get_candles(token: str, exchange: str, interval: str, from_str: str,
                to_str: str) -> list[list] | None:
    """Raw candles for one instrument and window.

    `interval` is a short key from CANDLE_INTERVALS ("1m", "1d", ...) or an Angel
    constant. Dates are "YYYY-MM-DD HH:MM" in IST, as Angel expects.

    Returns Angel's rows — [timestamp, open, high, low, close, volume] — or None when
    the call failed or the budget is exhausted. An empty list means the window really
    held no trades (a holiday, or a symbol that had not listed yet), which is a fact the
    calendar derivation depends on being able to tell apart from a failure.
    """
    ivl = CANDLE_INTERVALS.get(interval, interval)
    params = {"exchange": exchange, "symboltoken": str(token), "interval": ivl,
              "fromdate": from_str, "todate": to_str}
    try:
        resp = _call(lambda smart, p: smart.getCandleData(p), params, "candle", "getCandleData")
    except Exception as exc:
        log.warning("angel getCandleData error for token %s: %s", token, exc)
        return None
    if not resp:
        return None
    if not resp.get("status"):
        log.warning("angel getCandleData %s: %s", token, resp.get("message"))
        return None
    return resp.get("data") or []
