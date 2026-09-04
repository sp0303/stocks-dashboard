"""Corporate actions — fetch, parse, and normalize NSE/BSE corporate-action records.

Why this exists
---------------
A tradebook records *trades*, but a holding's real quantity is also changed by events
that are **not** trades: a stock split or bonus multiplies your shares (and divides the
per-share cost) with no buy/sell row, and a rename/demerger/merger moves a position under
a different ticker or ISIN. Without this data the FIFO engine's quantities drift away from
the broker's actual holdings (see engine.py's split/bonus adjustment).

Design
------
* Source of record is NSE's public corporate-actions endpoint (BSE is a future fallback).
  NSE blocks un-primed requests, so we prime a cookie off the homepage first, exactly like
  a browser. The call runs from the app process (which has normal internet), not the
  sandboxed dev tools.
* The free-text ``subject`` field is parsed into a typed action with a **quantity
  multiplier** for the two events that change share count (SPLIT, BONUS). Everything else
  (DIVIDEND, DEMERGER, MERGER, BUYBACK, DELISTING, RIGHTS) is normalized and stored but
  carries multiplier 1.0 — those need value/mapping handling, not a blind qty scale.
* Parsing is a pure function (``parse_action``) so it is unit-testable with no network.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime

import httpx

log = logging.getLogger("corporate_actions")

NSE_HOME = "https://www.nseindia.com"
NSE_CA = NSE_HOME + "/api/corporates-corporateActions"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": NSE_HOME + "/companies-listing/corporate-filings-actions",
}

# Action types we classify a `subject` string into.
SPLIT, BONUS, DIVIDEND, DEMERGER, MERGER, BUYBACK, DELISTING, RIGHTS, OTHER = (
    "SPLIT", "BONUS", "DIVIDEND", "DEMERGER", "MERGER", "BUYBACK", "DELISTING", "RIGHTS", "OTHER"
)
# Only these change share count and are safe to auto-apply as a quantity multiplier.
QTY_CHANGING = {SPLIT, BONUS}

_RS = r"(?:rs|re|inr)?\.?\s*/?-?\s*([\d]+(?:\.\d+)?)"  # a rupee amount, forgiving of Rs/Re/./- noise


def _iso(d: str | None) -> str | None:
    """NSE dates are '05-Jun-2026'; normalize to ISO 'YYYY-MM-DD'. Pass through junk as None."""
    if not d or d in ("-", "0", ""):
        return None
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_action(subject: str) -> dict:
    """Classify a corporate-action ``subject`` string into a typed action.

    Returns ``{type, qty_multiplier, amount_per_share, detail}``. ``qty_multiplier`` is the
    factor to scale an open position by on the ex-date (2.0 for a 1:1 bonus, 5.0 for a
    Rs10->Rs2 split); it is 1.0 for every non-qty-changing action. ``amount_per_share`` is
    filled for dividends. Parsing is deliberately forgiving of NSE's punctuation noise.
    """
    s = (subject or "").strip()
    low = s.lower()
    out = {"type": OTHER, "qty_multiplier": 1.0, "amount_per_share": None, "detail": s}

    # SPLIT — face-value sub-division, e.g. "Face Value Split ... From Rs 10/- To Rs 2/-".
    if ("split" in low or "sub-division" in low or "sub division" in low
            or ("face value" in low and "from" in low)):
        m = re.search(r"from\s+" + _RS + r".*?to\s+" + _RS, low)
        if m:
            old_fv, new_fv = float(m.group(1)), float(m.group(2))
            if new_fv > 0 and old_fv > new_fv:
                out.update(type=SPLIT, qty_multiplier=old_fv / new_fv)
                return out
        out["type"] = SPLIT  # a split we couldn't parse a ratio for — store, don't scale
        return out

    # BONUS — "Bonus A:B" = A new shares for every B held -> multiplier (A+B)/B.
    if "bonus" in low:
        m = re.search(r"bonus\s+(\d+)\s*:\s*(\d+)", low)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if b > 0:
                out.update(type=BONUS, qty_multiplier=(a + b) / b)
                return out
        out["type"] = BONUS
        return out

    if "demerger" in low or "de-merger" in low:
        out["type"] = DEMERGER
        return out
    if "buy back" in low or "buyback" in low or "buy-back" in low:
        out["type"] = BUYBACK
        return out
    if "amalgamation" in low or "merger" in low or "scheme of arrangement" in low:
        out["type"] = MERGER
        return out
    if "delisting" in low or "delist" in low:
        out["type"] = DELISTING
        return out
    if "rights" in low:
        out["type"] = RIGHTS
        return out
    if "dividend" in low:
        m = re.search(r"dividend[^0-9]*" + _RS, low)
        out.update(type=DIVIDEND, amount_per_share=float(m.group(1)) if m else None)
        return out
    return out  # AGM / EGM / results / other announcements — kept as OTHER


def _client() -> httpx.Client:
    c = httpx.Client(headers=_HEADERS, timeout=20, follow_redirects=True)
    try:
        c.get(NSE_HOME)  # prime cookies like a browser session
    except Exception as e:  # noqa: BLE001 — priming is best-effort; the CA call may still work
        log.warning("NSE cookie prime failed: %s", e)
    return c


def _normalize(rec: dict, source: str = "NSE") -> dict | None:
    """Turn one raw NSE record into our stored shape, or None if it isn't dateable/typed."""
    ex = _iso(rec.get("exDate"))
    parsed = parse_action(rec.get("subject", ""))
    if parsed["type"] == OTHER:
        return None  # AGMs / results etc. — not a holding-affecting corporate action
    isin = (rec.get("isin") or "").strip() or None
    symbol = (rec.get("symbol") or "").strip().upper() or None
    return {
        "isin": isin,
        "symbol": symbol,
        "ex_date": ex,
        "record_date": _iso(rec.get("recDate")),
        "type": parsed["type"],
        "qty_multiplier": round(parsed["qty_multiplier"], 8),
        "amount_per_share": parsed["amount_per_share"],
        "face_value": (rec.get("faceVal") or "").strip() or None,
        "series": (rec.get("series") or "").strip() or None,
        "subject": (rec.get("subject") or "").strip(),
        "company": (rec.get("comp") or "").strip() or None,
        "source": source,
        # stable identity for upsert/dedupe across refetches
        "key": f"{isin or symbol}|{ex}|{parsed['type']}|{(rec.get('subject') or '').strip()[:60]}",
        "fetched_at": datetime.utcnow().isoformat(),
    }


def fetch_nse_symbol(symbol: str, from_date: str = "01-01-2020",
                     to_date: str | None = None, client: httpx.Client | None = None) -> list[dict]:
    """Fetch normalized corporate actions for one NSE symbol over a date window.

    ``from_date``/``to_date`` are dd-mm-yyyy (NSE's format). Without a window NSE caps the
    response at ~20 rows, so a window is required to reach back to 2020.
    """
    to_date = to_date or date.today().strftime("%d-%m-%Y")
    own = client is None
    c = client or _client()
    try:
        params = {"index": "equities", "symbol": symbol,
                  "from_date": from_date, "to_date": to_date}
        r = c.get(NSE_CA, params=params)
        if r.status_code != 200:
            log.warning("NSE CA %s -> HTTP %s", symbol, r.status_code)
            return []
        raw = r.json()
        recs = raw if isinstance(raw, list) else raw.get("data", [])
        out = [n for n in (_normalize(rec) for rec in recs) if n]
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("NSE CA fetch failed for %s: %s", symbol, e)
        return []
    finally:
        if own:
            c.close()


def fetch_for_symbols(symbols: list[str], from_date: str = "01-01-2020",
                      to_date: str | None = None, pause: float = 0.4,
                      on_batch=None) -> list[dict]:
    """Fetch corporate actions for many symbols on one primed session, politely paced.

    Returns a flat, de-duplicated (by ``key``) list. Used by both the portfolio-scoped
    refresh and the market-wide background job. ``on_batch(symbol, records)`` is called
    after each symbol so a long market-wide run can persist incrementally.
    """
    c = _client()
    seen: dict[str, dict] = {}
    try:
        for i, sym in enumerate(symbols):
            recs = fetch_nse_symbol(sym, from_date, to_date, client=c)
            for rec in recs:
                seen[rec["key"]] = rec
            if on_batch:
                on_batch(sym, recs)
            if pause and i < len(symbols) - 1:
                time.sleep(pause)
    finally:
        c.close()
    return list(seen.values())


def fetch_all_nse_symbols() -> list[str]:
    """The full list of NSE-listed equity symbols, from the official EQUITY_L.csv.

    Used to drive the market-wide corporate-actions backfill. Returns [] on failure so the
    caller can fall back to the portfolio-scoped symbol set.
    """
    urls = [
        "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv",
        "https://www1.nseindia.com/content/equities/EQUITY_L.csv",
    ]
    c = _client()
    try:
        for url in urls:
            try:
                r = c.get(url)
                if r.status_code != 200 or not r.text:
                    continue
                lines = r.text.splitlines()
                header = [h.strip().upper() for h in lines[0].split(",")]
                try:
                    idx = header.index("SYMBOL")
                except ValueError:
                    idx = 0
                syms = []
                for line in lines[1:]:
                    parts = line.split(",")
                    if len(parts) > idx and parts[idx].strip():
                        syms.append(parts[idx].strip().upper())
                if syms:
                    return syms
            except Exception as e:  # noqa: BLE001
                log.warning("EQUITY_L fetch failed (%s): %s", url, e)
        return []
    finally:
        c.close()
