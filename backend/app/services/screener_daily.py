"""Broad (Nifty 500) screener data path.

Momentum / RSI / levels / ATR are computed from the daily OHLCV already stored in Mongo
(`orb_candles_1d`, one doc per symbol with a `rows` array) — so the whole 500-stock screen
costs ONE Mongo query and zero Angel calls. Fundamentals come from the pre-scraped
`nifty500_kpis.json` (Tijori FY26). Prices in the store are integers in paise (÷100 = ₹).

The daily store is refreshed by the ORB backfill / daily top-up; this module only reads it.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config import settings
from app.services.market_data import _levels, _rsi  # reuse the validated helpers

DAILY_COLL = "orb_candles_1d"
_KPI_PATH = Path(__file__).parent.parent / "data" / "nifty500_kpis.json"
_kpis_cache: dict | None = None


def _load_kpis() -> dict:
    global _kpis_cache
    if _kpis_cache is None:
        try:
            _kpis_cache = json.loads(_KPI_PATH.read_text())
        except Exception:
            _kpis_cache = {}
    return _kpis_cache


def _mongo():
    from pymongo import MongoClient
    return MongoClient(settings.mongodb_url)[settings.mongodb_db]


def _pct(a, b):
    return round((b - a) / a * 100, 2) if (a and b is not None) else None


def _metrics(rows: list[dict]) -> dict:
    """Momentum (1D/1W/1M/1Y), RSI(14), close-based levels, and a true ATR(14), from the
    daily OHLCV rows (paise → ₹)."""
    rows = [r for r in rows if r.get("c") is not None]
    if not rows:
        return {}
    closes = [r["c"] / 100 for r in rows]
    dates = [r["date"] for r in rows]
    last = closes[-1]
    now = datetime.now(timezone.utc)

    def ago(days):
        return (now - timedelta(days=days)).strftime("%Y-%m-%d")

    def close_on_or_before(target):
        for i in range(len(dates) - 1, -1, -1):
            if dates[i] <= target:
                return closes[i]
        return None

    prev = closes[-2] if len(closes) > 1 else None
    w = close_on_or_before(ago(7)); m = close_on_or_before(ago(30)); y = close_on_or_before(ago(365))
    win = [c for c, d in zip(closes, dates) if d >= ago(365)]
    hi = max(win) if win else None
    # 1Y only meaningful if the stock actually has ~a year of history (avoids IPO distortion)
    y1 = _pct(y, last) if (y and dates[0] <= ago(300)) else None

    atr = None
    if len(rows) >= 15:
        trs = []
        for i in range(len(rows) - 14, len(rows)):
            h = rows[i]["h"] / 100; l = rows[i]["l"] / 100; pc = rows[i - 1]["c"] / 100
            trs.append(max(h - l, abs(h - pc), abs(l - pc)))
        atr = round(sum(trs) / len(trs), 2)

    lv = _levels(closes)  # recent_high/low, range_position, dma20/50, typical_move_pct
    return {
        "price": round(last, 2),
        "d1": _pct(prev, last),
        "w1": _pct(w, last),
        "m1": _pct(m, last),
        "y1": y1,
        "from_52w_high": _pct(hi, last),
        "rsi": _rsi(closes),
        "volume": rows[-1].get("v"),
        "atr": atr,
        **lv,
    }


def _fundamentals(k: dict) -> dict:
    """Map a nifty500_kpis.json record to the screener's fundamentals shape."""
    pe = k.get("pe")
    return {
        "has_results": k.get("pat_cr") is not None,
        "market_cap_cr": k.get("mcap_cr"),
        "pe_label": (f"~{pe:.0f}x" if isinstance(pe, (int, float)) and pe >= 20
                     else f"~{pe:.1f}x" if isinstance(pe, (int, float)) else None),
        "rev_growth_label": "NII YoY" if k.get("is_banking") else "Revenue YoY",
        "rev_growth_pct": k.get("rev_yoy"),
        "margin_label": "NIM" if k.get("is_banking") else "EBITDA margin",
        "margin_pct": k.get("opm"),
        "pat_yoy_pct": k.get("pat_yoy"),
        "pat_yoy_label": (f"{'+' if (k.get('pat_yoy') or 0) >= 0 else ''}{k['pat_yoy']}% YoY"
                          if k.get("pat_yoy") is not None else None),
        "revenue_cr": k.get("rev_cr"),
        "ebitda_cr": k.get("ebitda_cr"),
        "pat_cr": k.get("pat_cr"),
        "note": None,
    }


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else None


def compute() -> dict:
    """Build the ranked broad-screener payload (same shape as the sector screener)."""
    kpis = _load_kpis()
    universe = [tk for tk, v in kpis.items() if not v.get("error") and tk != "DUMMYHEG"]

    # one Mongo query for all daily series
    daily = {}
    try:
        db = _mongo()
        for doc in db[DAILY_COLL].find({"_id": {"$in": universe}}, {"rows": 1}):
            daily[doc["_id"]] = doc.get("rows", [])
    except Exception:
        daily = {}

    # per-sector (NSE industry) average 1W for relative strength
    metrics_by_tk = {}
    sector_w1: dict[str, list[float]] = {}
    for tk in universe:
        rows = daily.get(tk)
        if not rows:
            continue
        mtr = _metrics(rows)
        if not mtr.get("price"):
            continue
        metrics_by_tk[tk] = mtr
        sec = kpis[tk].get("industry", "Other")
        if mtr.get("w1") is not None:
            sector_w1.setdefault(sec, []).append(mtr["w1"])
    sector_w1_avg = {s: sum(v) / len(v) for s, v in sector_w1.items() if v}

    stocks = []
    for tk, mtr in metrics_by_tk.items():
        k = kpis[tk]
        sec = k.get("industry", "Other")
        w1, m1, rsi = mtr.get("w1"), mtr.get("m1"), mtr.get("rsi")
        rel = (w1 - sector_w1_avg[sec]) if (w1 is not None and sec in sector_w1_avg) else None
        score = 0.0
        if w1 is not None:
            score += 0.45 * w1
        if m1 is not None:
            score += 0.25 * m1
        if rel is not None:
            score += 0.30 * rel
        if rsi is not None:
            if 50 <= rsi <= 65:
                score += 1.5
            elif rsi > 75:
                score -= 2.0
            elif rsi < 40:
                score -= 1.5
        stocks.append({
            "sector": sec, "ticker": tk, "name": k.get("name", tk),
            "price": mtr.get("price"), "d1": mtr.get("d1"), "w1": w1, "m1": m1,
            "y1": mtr.get("y1"), "from_52w_high": mtr.get("from_52w_high"),
            "rsi": rsi, "volume": mtr.get("volume"),
            "rel_strength": _round(rel), "score": _round(score),
            "fundamentals": _fundamentals(k),
            "levels": {
                "recent_high": mtr.get("recent_high"), "recent_low": mtr.get("recent_low"),
                "range_position": mtr.get("range_position"), "dma20": mtr.get("dma20"),
                "dma50": mtr.get("dma50"), "typical_move_pct": mtr.get("typical_move_pct"),
                "atr": mtr.get("atr"),
            },
        })

    stocks.sort(key=lambda s: (s["score"] is not None, s["score"] if s["score"] is not None else 0),
                reverse=True)
    for i, s in enumerate(stocks, 1):
        s["rank"] = i

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(stocks),
        "universe": len(universe),
        "stocks": stocks,
        "sectors": {s: _round(v) for s, v in sector_w1_avg.items()},
    }
