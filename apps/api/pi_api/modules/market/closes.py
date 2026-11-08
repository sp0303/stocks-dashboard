"""Latest-close lookup helpers (R6). Pure functions, no I/O.

Root cause of the "every board card is unpriced" bug: the batch lookup only
looked at closes from the last 30 calendar days, while holdings take the latest
close with no window. When the EOD sync lags (or a symbol trades thinly) every
watchlist/board symbol fell out of the window and rendered as unpriced, even
though the same security was priced on the holdings card. R6 says a stale
price must carry its ``as_of`` and be flagged, not silently dropped, so the
lookup now reaches back ``LOOKBACK_DAYS`` and marks staleness explicitly.

Symbols are also normalised (``NSE:TCS``, ``TCS.NS``, ``TCS-EQ`` -> ``TCS``)
because watchlists migrated from v1 and typed by users carry such forms, while
``market.securities`` stores the bare NSE/BSE symbol.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from pi_api.modules.market import health

LOOKBACK_DAYS = 400  # bounded time predicate (AGENTS §3.9); older than this = unpriced
STALE_AFTER_SESSIONS = 1  # a close more than one expected session old is stale
MAX_SYMBOLS = 200

_PREFIXES = ("NSE:", "BSE:", "NSE_EQ:", "BSE_EQ:")
_SUFFIXES = (".NS", ".BO", "-EQ", "-BE", "-BZ", "-SM", "-ST")


def normalise_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p):]
            break
    for suf in _SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s.strip()


def request_map(symbols: Iterable[str]) -> dict[str, list[str]]:
    """normalised symbol -> the requested spellings (upper-cased), capped at MAX_SYMBOLS."""
    out: dict[str, list[str]] = {}
    for raw in symbols:
        req = (raw or "").strip().upper()
        if not req:
            continue
        norm = normalise_symbol(req)
        if not norm:
            continue
        if norm not in out and len(out) >= MAX_SYMBOLS:
            continue
        spellings = out.setdefault(norm, [])
        if req not in spellings:
            spellings.append(req)
    return out


def staleness(
    price_date: date,
    sessions: list[date],
    last_session: date | None,
) -> tuple[int, bool]:
    behind = health.sessions_behind(price_date, sessions, last_session) or 0
    return behind, behind > STALE_AFTER_SESSIONS


def build_rows(
    found: list[dict],
    requested: dict[str, list[str]],
    sessions: list[date],
    last_session: date | None,
) -> list[dict]:
    """One row per requested spelling; symbols with no stored close are absent (R6)."""
    rows: list[dict] = []
    for f in found:
        behind, stale = staleness(f["price_date"], sessions, last_session)
        for req in requested.get(str(f["symbol"]).upper(), []):
            rows.append({
                **f,
                "symbol": req,
                "security_symbol": f["symbol"],
                "sessions_behind": behind,
                "is_stale": stale,
            })
    rows.sort(key=lambda r: r["symbol"])
    return rows
