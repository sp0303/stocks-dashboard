"""Market data behind a provider interface.

Quotes are cached in-process with a TTL so dashboard reads don't hammer the provider and
a brief outage degrades to a stale price, never to "no data". Angel One is the primary
provider (see AngelProvider / services.angel); Yahoo is the fallback. Providers sit behind
MarketDataProvider so adding/swapping one never touches callers.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod

from app.config import settings


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> dict[str, float]:
        """Return {SYMBOL: last_price}. Missing symbols are omitted."""


def _yf_ticker(symbol: str, exchange: str = "NSE") -> str:
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{symbol}{suffix}"


_CHART_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")


def _fetch_meta(ticker: str) -> dict | None:
    """Hit Yahoo's public chart endpoint directly (the yfinance library's crumb
    handling is unreliable on 0.2.x, but this endpoint is stable). Returns the
    meta block with regularMarketPrice / previousClose."""
    import httpx

    for host in _CHART_HOSTS:
        url = f"{host}/v8/finance/chart/{ticker}?range=5d&interval=1d"
        try:
            r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8.0)
            if r.status_code != 200:
                continue
            return r.json()["chart"]["result"][0]["meta"]
        except Exception:
            continue
    return None


def _fetch_one(ticker: str) -> float | None:
    meta = _fetch_meta(ticker)
    if not meta:
        return None
    px = meta.get("regularMarketPrice") or meta.get("previousClose")
    return round(float(px), 2) if px else None


_details_cache: dict[str, tuple[dict, float]] = {}  # symbol -> (details, ts)


def get_quote_details(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """Price + previous close + day change %, per symbol — per-symbol TTL cached (same
    window as get_quotes). This is what the watchlist and alert sweep call, so caching
    here is what keeps repeated watchlist loads during market hours from re-hitting the
    provider on every request. Only successful lookups are cached."""
    now = time.time()
    ttl = settings.quote_cache_ttl_seconds
    out: dict[str, dict] = {}
    need: list[str] = []
    for s in symbols:
        hit = _details_cache.get(s)
        if hit and now - hit[1] < ttl:
            out[s] = hit[0]
        else:
            need.append(s)
    if need:
        fetched = _fetch_quote_details(need, exchanges)
        for s in need:
            if s in fetched:
                _details_cache[s] = (fetched[s], now)
                out[s] = fetched[s]
    return out


def _fetch_quote_details(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """Angel One (exact NSE/BSE prices) first when configured; any symbol Angel can't
    price falls back to Yahoo, so the watchlist/detail views degrade rather than blank."""
    from app.services import angel

    exchanges = exchanges or {}
    out: dict[str, dict] = {}
    if angel.is_enabled():
        out.update(angel.quote_details(symbols, exchanges))
    missing = [s for s in symbols if s not in out]
    if missing:
        out.update(_yf_quote_details(missing, exchanges))
    return out


def _yf_quote_details(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """Yahoo-Finance fallback for get_quote_details."""
    from concurrent.futures import ThreadPoolExecutor

    exchanges = exchanges or {}

    def resolve(sym: str) -> tuple[str, dict]:
        primary = _yf_ticker(sym, exchanges.get(sym, "NSE"))
        meta = _fetch_meta(primary)
        if not meta or not (meta.get("regularMarketPrice") or meta.get("previousClose")):
            alt = f"{sym}.BO" if primary.endswith(".NS") else f"{sym}.NS"
            meta = _fetch_meta(alt) or meta
        if not meta:
            return sym, {"price": None, "prev_close": None, "change": None, "change_pct": None}
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose")
        volume = meta.get("regularMarketVolume")
        day_high = meta.get("regularMarketDayHigh")
        day_low = meta.get("regularMarketDayLow")
        change = round(price - prev, 2) if (price is not None and prev is not None) else None
        change_pct = round(change / prev * 100, 2) if (change is not None and prev) else None
        return sym, {
            "price": round(price, 2) if price is not None else None,
            "prev_close": round(prev, 2) if prev is not None else None,
            "change": change,
            "change_pct": change_pct,
            "volume": volume,
            "day_high": round(day_high, 2) if day_high is not None else None,
            "day_low": round(day_low, 2) if day_low is not None else None,
        }

    out: dict[str, dict] = {}
    if not symbols:
        return out
    with ThreadPoolExecutor(max_workers=12) as ex:
        for sym, d in ex.map(resolve, symbols):
            out[sym] = d
    return out


def _history_stats(points: list[dict]) -> dict:
    if not points:
        return {}
    closes = [p["close"] for p in points]
    return {
        "period_high": max(closes),
        "period_low": min(closes),
        "start_close": points[0]["close"],
        "end_close": points[-1]["close"],
        "change_pct": round((points[-1]["close"] - points[0]["close"]) / points[0]["close"] * 100, 2)
        if points[0]["close"] else None,
    }


_history_cache: dict[tuple, tuple[dict, float]] = {}  # (sym,from,interval,exch) -> (result, ts)
_HISTORY_TTL = max(settings.quote_cache_ttl_seconds, 1800)  # ≥30 min


def get_history(symbol: str, from_date: str | None = None, interval: str = "1d",
                exchange: str = "NSE") -> dict:
    """Cached wrapper — daily candles change at most once/day, so a 30-min TTL keeps
    repeated chart views and back-date lookups from re-hitting the provider (protects
    Angel's per-minute/hour quota). Only non-empty results are cached."""
    key = (symbol.upper(), from_date, interval, exchange)
    hit = _history_cache.get(key)
    if hit and time.time() - hit[1] < _HISTORY_TTL:
        return hit[0]
    result = _get_history(symbol, from_date, interval, exchange)
    if result.get("points"):
        _history_cache[key] = (result, time.time())
    return result


def _get_history(symbol: str, from_date: str | None = None, interval: str = "1d",
                 exchange: str = "NSE") -> dict:
    """Daily (or 1wk/1mo) OHLC-close history from `from_date` to now.

    Angel One (free candles) is tried first when configured; Yahoo is the fallback.
    Yahoo caps intraday intervals (1m=7d, 5m/15m=60d, 1h=730d) but daily/weekly/monthly
    reach back years, so `1d` is safe for any from-date. Returns {points:[{date,close}], ...}.
    """
    import time
    from datetime import datetime, timezone

    import httpx

    if interval not in ("1d", "1wk", "1mo"):
        interval = "1d"

    from app.services import angel
    if angel.is_enabled():
        pts = angel.get_history(symbol, from_date, interval, exchange)
        if pts:
            return {"symbol": symbol, "interval": interval, "from": from_date,
                    "points": pts, "stats": _history_stats(pts)}

    try:
        p1 = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) if from_date else int(time.time()) - 365 * 86400
    except ValueError:
        p1 = int(time.time()) - 365 * 86400
    p2 = int(time.time())

    def fetch(ticker: str):
        for host in _CHART_HOSTS:
            url = (f"{host}/v8/finance/chart/{ticker}"
                   f"?period1={p1}&period2={p2}&interval={interval}")
            try:
                r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12.0)
                if r.status_code != 200:
                    continue
                return r.json()["chart"]["result"][0]
            except Exception:
                continue
        return None

    primary = _yf_ticker(symbol, exchange)
    res = fetch(primary)
    if not res or "timestamp" not in res:
        res = fetch(f"{symbol}.BO" if primary.endswith(".NS") else f"{symbol}.NS")
    if not res or "timestamp" not in res:
        return {"symbol": symbol, "interval": interval, "points": []}

    ts = res["timestamp"]
    closes = res["indicators"]["quote"][0].get("close", [])
    points = [
        {"date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"),
         "close": round(float(c), 2)}
        for t, c in zip(ts, closes) if c is not None
    ]
    return {"symbol": symbol, "interval": interval, "from": from_date,
            "points": points, "stats": _history_stats(points)}


def get_dividend_history(symbol: str, exchange: str = "NSE", from_date: str | None = None) -> list[dict]:
    """Ex-date + per-share dividend amount from Yahoo's chart endpoint (`events=div`).
    Used only to generate suggestions for the user to confirm — never written straight
    into the dividends collection, since we don't know held quantity on the ex-date here.
    """
    from datetime import datetime, timezone

    import httpx

    try:
        p1 = int(datetime.strptime(from_date, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()) if from_date else int(time.time()) - 5 * 365 * 86400
    except ValueError:
        p1 = int(time.time()) - 5 * 365 * 86400
    p2 = int(time.time())

    def fetch(ticker: str):
        for host in _CHART_HOSTS:
            url = (f"{host}/v8/finance/chart/{ticker}"
                   f"?period1={p1}&period2={p2}&interval=1d&events=div")
            try:
                r = httpx.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=12.0)
                if r.status_code != 200:
                    continue
                return r.json()["chart"]["result"][0]
            except Exception:
                continue
        return None

    primary = _yf_ticker(symbol, exchange)
    res = fetch(primary)
    if not res or "events" not in res:
        res = fetch(f"{symbol}.BO" if primary.endswith(".NS") else f"{symbol}.NS")
    if not res or "events" not in res:
        return []

    divs = res.get("events", {}).get("dividends", {})
    out = [
        {
            "ex_date": datetime.fromtimestamp(d["date"], tz=timezone.utc).strftime("%Y-%m-%d"),
            "amount_per_share": round(float(d["amount"]), 4),
        }
        for d in divs.values()
    ]
    out.sort(key=lambda d: d["ex_date"])
    return out


class YFinanceProvider(MarketDataProvider):
    """Yahoo Finance quotes via the direct chart API (NSE `.NS`, BSE `.BO` fallback)."""

    def get_quotes(self, symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, float]:
        if not symbols:
            return {}
        from concurrent.futures import ThreadPoolExecutor

        exchanges = exchanges or {}

        def resolve(sym: str) -> tuple[str, float | None]:
            primary = _yf_ticker(sym, exchanges.get(sym, "NSE"))
            px = _fetch_one(primary)
            if px is None:  # try the other exchange suffix
                alt = f"{sym}.BO" if primary.endswith(".NS") else f"{sym}.NS"
                px = _fetch_one(alt)
            return sym, px

        out: dict[str, float] = {}
        with ThreadPoolExecutor(max_workers=12) as ex:
            for sym, px in ex.map(resolve, symbols):
                if px is not None:
                    out[sym] = px
        return out


class AngelProvider(MarketDataProvider):
    """Angel One SmartAPI quotes — free, programmatic login, exact NSE/BSE prices."""

    def get_quotes(self, symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, float]:
        from app.services import angel

        if not symbols or not angel.is_enabled():
            return {}
        return angel.get_quotes(symbols, exchanges or {})


class CompositeProvider(MarketDataProvider):
    """Try each provider in priority order (Angel, then Yahoo), asking each only for the
    symbols the previous ones couldn't price. Switching brokers never loses coverage for
    an odd symbol — Yahoo remains the last-resort backstop."""

    def __init__(self, *providers: MarketDataProvider):
        self.providers = providers

    def get_quotes(self, symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, float]:
        out: dict[str, float] = {}
        remaining = list(symbols)
        for p in self.providers:
            if not remaining:
                break
            got = p.get_quotes(remaining, exchanges)  # type: ignore[call-arg]
            out.update(got)
            remaining = [s for s in remaining if s not in out]
        return out


class QuoteCache:
    """Caches both hits and misses.

    A symbol Yahoo can't resolve (delisted, a rights entitlement, an obscure
    instrument with no real ticker) used to be dropped by the provider and
    therefore never cached — every single request would retry the full
    network round-trip for it, forever. That's a fixed multi-second tax on
    every page load that includes such a symbol. Failed lookups are now
    cached too, just with a shorter TTL, so they're retried occasionally
    (in case the symbol becomes resolvable later) instead of on every request.
    """

    def __init__(self, provider: MarketDataProvider, ttl: int, negative_ttl: int | None = None):
        self.provider = provider
        self.ttl = ttl
        self.negative_ttl = negative_ttl if negative_ttl is not None else min(ttl, 300)
        self._cache: dict[str, tuple[float | None, float]] = {}  # sym -> (price or None, ts)

    def _ttl_for(self, price: float | None) -> int:
        return self.ttl if price is not None else self.negative_ttl

    def get(self, symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
        now = time.time()
        fresh = {
            s: v for s, (v, ts) in self._cache.items()
            if s in symbols and now - ts < self._ttl_for(v)
        }
        need = [s for s in symbols if s not in fresh]
        if need:
            fetched = self.provider.get_quotes(need, exchanges)  # type: ignore[call-arg]
            for s in need:
                self._cache[s] = (fetched.get(s), now)
        result: dict[str, dict] = {}
        for s in symbols:
            if s in self._cache:
                price, ts = self._cache[s]
                result[s] = {"price": price, "as_of": ts, "stale": (now - ts) >= self._ttl_for(price)}
            else:
                result[s] = {"price": None, "as_of": None, "stale": True}
        return result


# Angel One first (free, exact NSE/BSE), Yahoo as the final backstop.
_cache = QuoteCache(
    CompositeProvider(AngelProvider(), YFinanceProvider()),
    settings.quote_cache_ttl_seconds,
)


def get_quotes(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    return _cache.get(symbols, exchanges)


def _pct(a: float | None, b: float | None) -> float | None:
    """% change from a to b."""
    if a is None or b is None or a == 0:
        return None
    return round((b - a) / a * 100, 2)


def _closest_on_or_before(points: list[dict], target_date: str) -> dict | None:
    """Last point with date <= target_date (exchanges are closed on weekends/holidays,
    so 'N days ago' rarely lands on a trading day exactly)."""
    candidates = [p for p in points if p["date"] <= target_date]
    return candidates[-1] if candidates else None


def _rsi(closes: list[float], period: int = 14) -> float | None:
    """Wilder's 14-period RSI from a series of daily closes (oldest→newest).
    Returns None when there isn't enough history (< period+1 closes)."""
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    # Wilder smoothing across the remaining deltas
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def _price_matrix_one(symbol: str, exchange: str) -> dict:
    """1D/1W/1M/1Y % change + % off the 52-week high + RSI(14), all derived from the
    same daily-close history used for the watchlist/stock-detail charts — no separate feed."""
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    hist = get_history(symbol, from_date=(now - timedelta(days=380)).strftime("%Y-%m-%d"),
                        interval="1d", exchange=exchange)
    points = hist.get("points", [])
    if not points:
        return {"price": None, "d1": None, "w1": None, "m1": None, "y1": None,
                "from_52w_high": None, "rsi": None}

    latest = points[-1]
    prev = points[-2] if len(points) > 1 else None
    w1_ref = _closest_on_or_before(points[:-1], (now - timedelta(days=7)).strftime("%Y-%m-%d"))
    m1_ref = _closest_on_or_before(points[:-1], (now - timedelta(days=30)).strftime("%Y-%m-%d"))
    y1_ref = _closest_on_or_before(points[:-1], (now - timedelta(days=365)).strftime("%Y-%m-%d"))

    window_52w = [p["close"] for p in points if p["date"] >= (now - timedelta(days=365)).strftime("%Y-%m-%d")]
    high_52w = max(window_52w) if window_52w else None

    return {
        "price": latest["close"],
        "d1": _pct(prev["close"], latest["close"]) if prev else None,
        "w1": _pct(w1_ref["close"], latest["close"]) if w1_ref else None,
        "m1": _pct(m1_ref["close"], latest["close"]) if m1_ref else None,
        # a name listed < 1 year ago has no real 1Y reference — leave it null rather
        # than compare against its IPO-week price and imply a misleading return
        "y1": _pct(y1_ref["close"], latest["close"]) if (y1_ref and y1_ref["date"] <= (now - timedelta(days=300)).strftime("%Y-%m-%d")) else None,
        "from_52w_high": _pct(high_52w, latest["close"]) if high_52w else None,
        "rsi": _rsi([p["close"] for p in points]),
    }


class _TTLCache:
    def __init__(self, ttl: int):
        self.ttl = ttl
        self._cache: dict[str, tuple[dict, float]] = {}

    def get_many(self, keys: list[str], compute: dict[str, "callable"]) -> dict[str, dict]:
        now = time.time()
        out: dict[str, dict] = {}
        need: list[str] = []
        for k in keys:
            hit = self._cache.get(k)
            if hit and now - hit[1] < self.ttl:
                out[k] = hit[0]
            else:
                need.append(k)
        if need:
            from concurrent.futures import ThreadPoolExecutor

            with ThreadPoolExecutor(max_workers=12) as ex:
                results = list(ex.map(lambda k: (k, compute[k]()), need))
            for k, v in results:
                self._cache[k] = (v, now)
                out[k] = v
        return out


_price_matrix_cache = _TTLCache(ttl=max(settings.quote_cache_ttl_seconds, 1800))


def get_price_matrix(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """1D/1W/1M/1Y momentum + distance from 52-week high, per symbol. Cached longer than
    live quotes since it's a heavier computation (a full year of daily candles per symbol)
    and doesn't need to be second-fresh."""
    exchanges = exchanges or {}
    compute = {s: (lambda sym=s: _price_matrix_one(sym, exchanges.get(sym, "NSE"))) for s in symbols}
    return _price_matrix_cache.get_many(symbols, compute)
