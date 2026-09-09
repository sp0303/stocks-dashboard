"""Nightly reconciliation: our live-built bars against Angel's own candles.

A dropped websocket connection does not produce missing bars — it produces *wrong*
ones, and nothing flags them. That is the failure this exists to catch. After the close
we re-fetch the day from REST, compare minute by minute, repair what disagrees, and
write down how much had to be repaired.

That agreement percentage is Segment B's exit test. Until it sits above 99.5% for five
consecutive sessions, the strategy layer stays switched off.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app.services.orb import store
from app.services.orb.bars import Bar, densify
from app.services.orb.history import fetch_minute_window
from app.services.orb.session import IST, MARKET_CLOSE, MARKET_OPEN
from app.services.orb.universe import Instrument

log = logging.getLogger("orb.recon")

VOLUME_TOLERANCE = 0.01      # 1% — a boundary tick landing either side of a second


def compare(ours: list[Bar], theirs: list[Bar]) -> dict:
    """Compare on the minutes Angel says actually traded.

    Angel omits minutes with no trades; we synthesise them. Aligning positionally would
    compare unrelated bars, so this aligns on the minute key and judges only where the
    exchange recorded trading."""
    mine = {b.minute: b for b in ours}
    ref = {b.minute: b for b in theirs if not b.syn}
    compared = matched = price_ok = missing = 0
    diffs: list[dict] = []
    for m, t in sorted(ref.items()):
        compared += 1
        o = mine.get(m)
        if o is None or o.syn:
            missing += 1
            diffs.append({"m": m, "why": "missing" if o is None else "synthetic"})
            continue
        ohlc_ok = (o.o, o.h, o.l, o.c) == (t.o, t.h, t.l, t.c)
        vol_ok = t.v == 0 or abs(o.v - t.v) <= max(1, VOLUME_TOLERANCE * t.v)
        price_ok += 1 if ohlc_ok else 0
        if ohlc_ok and vol_ok:
            matched += 1
        elif len(diffs) < 25:
            diffs.append({"m": m, "ours": [o.o, o.h, o.l, o.c, o.v],
                          "theirs": [t.o, t.h, t.l, t.c, t.v]})
    return {
        "compared": compared, "matched": matched, "missing": missing,
        "agree_pct": round(matched / compared * 100, 3) if compared else None,
        "price_agree_pct": round(price_ok / compared * 100, 3) if compared else None,
        "diffs": diffs,
    }


def reconcile_symbol(inst: Instrument, day: str, repair: bool = True) -> dict | None:
    """Returns the comparison for one symbol-day, having repaired it if asked."""
    d = date.fromisoformat(day)
    by_day = fetch_minute_window(inst, d, d)
    if by_day is None:
        return None                                  # call failed; try again later
    theirs_raw = by_day.get(day, [])
    if not theirs_raw:
        return {"compared": 0, "matched": 0, "missing": 0, "agree_pct": None,
                "note": "Angel returned no candles for this session"}
    ours = store.load_session(inst.symbol, day)
    theirs = densify(theirs_raw, MARKET_OPEN, MARKET_CLOSE)
    result = compare(ours, theirs)
    if repair and (result["agree_pct"] is None or result["agree_pct"] < 100.0):
        last_real = max(b.minute for b in theirs_raw)
        store.save_session(inst.symbol, day, theirs, src="rest-repaired",
                           last_real=last_real, real_bars=len(theirs_raw),
                           repaired_at=datetime.now(IST).isoformat(),
                           agree_pct=result["agree_pct"])
        result["repaired"] = True
    return result


def reconcile_day(instruments: list[Instrument], day: str, repair: bool = True) -> dict:
    """The 15:40 job. Angel is authoritative: where the two disagree, the stored session
    is replaced with Angel's, and the disagreement is recorded rather than discarded."""
    per_symbol, failures = {}, []
    total_compared = total_matched = repaired = 0
    for inst in instruments:
        try:
            r = reconcile_symbol(inst, day, repair)
        except Exception as exc:
            log.exception("reconcile failed for %s", inst.symbol)
            failures.append(f"{inst.symbol}: {exc}")
            continue
        if r is None:
            failures.append(f"{inst.symbol}: candle fetch failed")
            continue
        per_symbol[inst.symbol] = {k: v for k, v in r.items() if k != "diffs"}
        total_compared += r["compared"]
        total_matched += r["matched"]
        repaired += 1 if r.get("repaired") else 0

    agree = round(total_matched / total_compared * 100, 3) if total_compared else None
    worst = sorted((s for s in per_symbol.items() if s[1].get("agree_pct") is not None),
                   key=lambda kv: kv[1]["agree_pct"])[:10]
    doc = {
        "_id": day, "date": day, "symbols": len(per_symbol),
        "minutes_compared": total_compared, "minutes_matched": total_matched,
        "agree_pct": agree, "repaired_symbols": repaired,
        "failures": failures[:50],
        "worst": [{"sym": s, **v} for s, v in worst],
        "passes_exit_test": bool(agree is not None and agree >= 99.5),
        "at": datetime.now(IST).isoformat(),
    }
    store.put(store.HEALTH, doc)
    log.info("reconciliation %s: %s%% over %d minutes, %d symbols repaired",
             day, agree, total_compared, repaired)
    return doc


def recent_health(n: int = 10) -> list[dict]:
    rows = store.find(store.HEALTH, {"date": {"$exists": True}},
                      sort=[("date", -1)], limit=n)
    return [{k: v for k, v in r.items() if k not in ("worst", "failures")} for r in rows]


def exit_test(sessions: int = 5) -> dict:
    """Segment B stage 1's gate, as a number: five consecutive sessions at or above
    99.5% agreement."""
    rows = [r for r in recent_health(sessions) if r.get("agree_pct") is not None]
    passing = [r for r in rows if r["agree_pct"] >= 99.5]
    return {
        "sessions_required": sessions, "sessions_scored": len(rows),
        "sessions_passing": len(passing),
        "worst_agree_pct": min((r["agree_pct"] for r in rows), default=None),
        "passed": len(rows) >= sessions and len(passing) == len(rows),
    }
