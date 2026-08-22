"""Market data behind a provider interface.

Only the backend talks to yfinance. Quotes are cached in-process with a TTL so dashboard
reads don't hammer Yahoo and a brief outage degrades to a stale price, never to "no data".
Swap YFinanceProvider for a KiteProvider later without touching callers.
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
    if exchange.upper() == "INDEX":
        return symbol  # raw ticker, e.g. ^NSEI, ^BSESN — no NSE/BSE suffix
    suffix = ".BO" if exchange.upper() == "BSE" else ".NS"
    return f"{symbol}{suffix}"


# Well-known Indian benchmark indices, keyed by a short id used across the API.
BENCHMARKS = {
    "nifty50": {"label": "Nifty 50", "ticker": "^NSEI"},
    "sensex": {"label": "Sensex", "ticker": "^BSESN"},
}


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


def get_quote_details(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    """For the watchlist: price + previous close + day change %."""
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
        change = round(price - prev, 2) if (price is not None and prev is not None) else None
        change_pct = round(change / prev * 100, 2) if (change is not None and prev) else None
        return sym, {
            "price": round(price, 2) if price is not None else None,
            "prev_close": round(prev, 2) if prev is not None else None,
            "change": change,
            "change_pct": change_pct,
        }

    out: dict[str, dict] = {}
    if not symbols:
        return out
    with ThreadPoolExecutor(max_workers=12) as ex:
        for sym, d in ex.map(resolve, symbols):
            out[sym] = d
    return out


def get_history(symbol: str, from_date: str | None = None, interval: str = "1d",
                exchange: str = "NSE") -> dict:
    """Daily (or 1wk/1mo) OHLC-close history from `from_date` to now.

    Yahoo caps intraday intervals (1m=7d, 5m/15m=60d, 1h=730d) but daily/weekly/monthly
    reach back years, so `1d` is safe for any from-date. Returns {points:[{date,close}], ...}.
    """
    import time
    from datetime import datetime, timezone

    import httpx

    if interval not in ("1d", "1wk", "1mo"):
        interval = "1d"
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
    if exchange.upper() != "INDEX" and (not res or "timestamp" not in res):
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
    highs = [p["close"] for p in points]
    stats = {}
    if points:
        stats = {
            "period_high": max(highs),
            "period_low": min(highs),
            "start_close": points[0]["close"],
            "end_close": points[-1]["close"],
            "change_pct": round((points[-1]["close"] - points[0]["close"]) / points[0]["close"] * 100, 2)
            if points[0]["close"] else None,
        }
    return {"symbol": symbol, "interval": interval, "from": from_date, "points": points, "stats": stats}


def get_checkpoint_prices(entries: list[tuple[str, str]], exchanges: dict[str, str] | None = None) -> dict[str, float | None]:
    """For watchlist checkpoints: close price on (or just after) each (symbol, date).

    `entries` is a list of (symbol, checkpoint_date) pairs. Threaded — one history
    fetch per entry, each already efficient (single daily-series call per symbol).
    """
    from concurrent.futures import ThreadPoolExecutor

    exchanges = exchanges or {}

    def fetch(pair):
        symbol, date = pair
        h = get_history(symbol, from_date=date, interval="1d", exchange=exchanges.get(symbol, "NSE"))
        pts = h.get("points") or []
        return symbol, (pts[0]["close"] if pts else None)

    out: dict[str, float | None] = {}
    if not entries:
        return out
    with ThreadPoolExecutor(max_workers=10) as ex:
        for symbol, price in ex.map(fetch, entries):
            out[symbol] = price
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


class QuoteCache:
    def __init__(self, provider: MarketDataProvider, ttl: int):
        self.provider = provider
        self.ttl = ttl
        self._cache: dict[str, tuple[float, float]] = {}  # sym -> (price, ts)

    def get(self, symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
        now = time.time()
        fresh = {s: v for s, (v, ts) in self._cache.items() if s in symbols and now - ts < self.ttl}
        need = [s for s in symbols if s not in fresh]
        if need:
            fetched = self.provider.get_quotes(need, exchanges)  # type: ignore[call-arg]
            for s, v in fetched.items():
                self._cache[s] = (v, now)
        result: dict[str, dict] = {}
        for s in symbols:
            if s in self._cache:
                price, ts = self._cache[s]
                result[s] = {"price": price, "as_of": ts, "stale": (now - ts) >= self.ttl}
            else:
                result[s] = {"price": None, "as_of": None, "stale": True}
        return result


_cache = QuoteCache(YFinanceProvider(), settings.quote_cache_ttl_seconds)


def get_quotes(symbols: list[str], exchanges: dict[str, str] | None = None) -> dict[str, dict]:
    return _cache.get(symbols, exchanges)
