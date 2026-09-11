"""MongoDB persistence for the ORB engine.

One document per symbol per session, holding the whole day as parallel arrays. Twenty
million minute bars as twenty million documents would be dominated by per-document and
index overhead; bucketed this way it is about 100,000 documents, each read exactly the
way the engine uses it — a whole session at a time.

Synchronous pymongo on purpose. The backfill is a two-hour batch job and the live
engine runs in its own thread alongside blocking Angel calls; neither belongs on the
app's event loop. Routers reach this through run_in_threadpool.

Prices are integer paise everywhere. Minutes are minute-of-day IST.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any, Iterable

from pymongo import ASCENDING, MongoClient

from app.config import settings
from app.services.orb.bars import Bar
from app.services.orb.session import MARKET_CLOSE, MARKET_OPEN

log = logging.getLogger("orb.store")

CANDLES_1M = "orb_candles_1m"
CANDLES_1D = "orb_candles_1d"
CALENDAR = "orb_calendar"
UNIVERSE = "orb_universe"
HEALTH = "orb_health"
SIGNALS = "orb_signals"
JOURNAL = "orb_journal"
JOBS = "orb_jobs"
BACKFILL = "orb_backfill"

_client: MongoClient | None = None


class StoreUnavailable(RuntimeError):
    """Raised when MONGODB_URL is not configured. The ORB engine needs a real database:
    unlike the rest of the app it has no JSON-file fallback, because a two-year minute
    series is not something to keep in a single JSON blob."""


def get_db():
    global _client
    if not settings.mongodb_url.strip():
        raise StoreUnavailable("MONGODB_URL is not set — the ORB engine requires MongoDB")
    if _client is None:
        _client = MongoClient(settings.mongodb_url, tz_aware=False)
    return _client[settings.mongodb_db]


def ensure_indexes() -> None:
    db = get_db()
    db[CANDLES_1M].create_index([("date", ASCENDING), ("sym", ASCENDING)])
    db[SIGNALS].create_index([("date", ASCENDING), ("sym", ASCENDING)])
    db[JOURNAL].create_index([("date", ASCENDING)])
    db[BACKFILL].create_index([("sym", ASCENDING)])
    log.info("orb indexes ensured")


# ── 1-minute candles ──────────────────────────────────────────────
def _key(sym: str, day: str) -> str:
    return f"{sym}:{day}"


def bars_to_doc(sym: str, day: str, bars: Iterable[Bar], src: str,
                session_end: int = MARKET_CLOSE) -> dict:
    rows = sorted(bars, key=lambda b: b.minute)
    return {
        "_id": _key(sym, day), "sym": sym, "date": day, "exch": "NSE", "src": src,
        "t": [b.minute for b in rows],
        "o": [b.o for b in rows], "h": [b.h for b in rows],
        "l": [b.l for b in rows], "c": [b.c for b in rows],
        "v": [b.v for b in rows],
        "syn": [b.syn for b in rows],
        "n": len(rows), "session_end": session_end,
    }


def doc_to_bars(doc: dict | None) -> list[Bar]:
    if not doc or not doc.get("t"):
        return []
    syn = doc.get("syn") or [False] * doc["n"]
    return [Bar(minute=doc["t"][i], o=doc["o"][i], h=doc["h"][i], l=doc["l"][i],
                c=doc["c"][i], v=doc["v"][i], syn=bool(syn[i]))
            for i in range(len(doc["t"]))]


def save_session(sym: str, day: str, bars: Iterable[Bar], src: str = "rest",
                 session_end: int = MARKET_CLOSE, **extra) -> None:
    """Replace a whole symbol-day. Idempotent by construction — the natural _id means
    re-running a backfill chunk converges instead of duplicating."""
    doc = bars_to_doc(sym, day, bars, src, session_end)
    doc.update(extra)
    get_db()[CANDLES_1M].replace_one({"_id": doc["_id"]}, doc, upsert=True)


def merge_bars(sym: str, day: str, bars: Iterable[Bar], src: str = "ws") -> None:
    """Write bars into an existing session document without losing the ones already
    there. This is the live path: the recorder flushes a handful of minutes at a time."""
    rows = sorted(bars, key=lambda b: b.minute)
    if not rows:
        return
    col = get_db()[CANDLES_1M]
    doc = col.find_one({"_id": _key(sym, day)})
    existing = {b.minute: b for b in doc_to_bars(doc)}
    for b in rows:
        existing[b.minute] = b
    merged = bars_to_doc(sym, day, existing.values(), src,
                         (doc or {}).get("session_end", MARKET_CLOSE))
    if doc and doc.get("repaired_at"):
        merged["repaired_at"] = doc["repaired_at"]
    col.replace_one({"_id": merged["_id"]}, merged, upsert=True)


def load_session(sym: str, day: str) -> list[Bar]:
    return doc_to_bars(get_db()[CANDLES_1M].find_one({"_id": _key(sym, day)}))


def load_sessions(sym: str, days: list[str]) -> dict[str, list[Bar]]:
    ids = [_key(sym, d) for d in days]
    return {doc["date"]: doc_to_bars(doc)
            for doc in get_db()[CANDLES_1M].find({"_id": {"$in": ids}})}


def sessions_present(sym: str) -> set[str]:
    return {d["date"] for d in
            get_db()[CANDLES_1M].find({"sym": sym}, {"date": 1, "_id": 0})}


def symbols_with_data(day: str) -> list[str]:
    return [d["sym"] for d in
            get_db()[CANDLES_1M].find({"date": day}, {"sym": 1, "_id": 0})]


def session_coverage(day: str) -> list[dict]:
    """Per-symbol bar counts for one day — the input to the health report."""
    return list(get_db()[CANDLES_1M].find(
        {"date": day},
        {"sym": 1, "n": 1, "src": 1, "syn": 1, "last_real": 1, "real_bars": 1, "_id": 0}))


# ── daily candles ─────────────────────────────────────────────────
def save_daily(sym: str, rows: list[dict]) -> int:
    """rows: [{date, o, h, l, c, v}] in paise.

    Bucketed one document per *symbol*, same reasoning as the minute store: five years
    of daily bars is ~1,250 entries, and the engine always wants a whole history at
    once (ATR, liquidity ranking, previous-day levels). Merges with what is already
    stored so a shorter re-fetch never truncates a longer history."""
    if not rows:
        return 0
    col = get_db()[CANDLES_1D]
    existing = col.find_one({"_id": sym}) or {}
    merged = {r["date"]: r for r in existing.get("rows", [])}
    merged.update({r["date"]: r for r in rows})
    ordered = [merged[d] for d in sorted(merged)]
    col.replace_one({"_id": sym},
                    {"_id": sym, "sym": sym, "n": len(ordered), "rows": ordered},
                    upsert=True)
    return len(ordered)


def load_daily(sym: str, limit: int | None = None) -> list[dict]:
    doc = get_db()[CANDLES_1D].find_one({"_id": sym})
    rows = (doc or {}).get("rows", [])
    return rows[-limit:] if limit else rows


def daily_symbols() -> list[str]:
    return [d["_id"] for d in get_db()[CANDLES_1D].find({}, {"_id": 1})]


# ── generic keyed documents ───────────────────────────────────────
def put(collection: str, doc: dict) -> None:
    get_db()[collection].replace_one({"_id": doc["_id"]}, doc, upsert=True)


def get(collection: str, _id: Any) -> dict | None:
    return get_db()[collection].find_one({"_id": _id})


def find(collection: str, query: dict, sort: list | None = None,
         limit: int = 0) -> list[dict]:
    cur = get_db()[collection].find(query)
    if sort:
        cur = cur.sort(sort)
    if limit:
        cur = cur.limit(limit)
    return list(cur)


def status() -> dict:
    """Cheap health summary for /api/orb/status."""
    try:
        db = get_db()
        return {
            "connected": True,
            "sessions_1m": db[CANDLES_1M].estimated_document_count(),
            "daily_symbols": db[CANDLES_1D].estimated_document_count(),
            "trading_days": db[CALENDAR].count_documents({"trading": True}),
            "signals": db[SIGNALS].estimated_document_count(),
        }
    except StoreUnavailable as exc:
        return {"connected": False, "error": str(exc)}
    except Exception as exc:                                    # pragma: no cover
        return {"connected": False, "error": str(exc)}
