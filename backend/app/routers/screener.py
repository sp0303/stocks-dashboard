"""Swing-trade screener — a read-only, decision-support view over the sector universe.

Ranks every sector-covered stock on transparent technical metrics (short-term momentum,
relative strength vs its own sector, RSI, and traded volume) so a user can spot candidates
themselves. It intentionally makes NO buy/sell recommendation and computes no target price —
it surfaces the raw numbers and a transparent momentum score, and the user decides.

Data source: the same daily-close history + live quotes used everywhere else
(Angel One SmartAPI with Yahoo fallback), via app.services.market_data.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.routers.sectors import SECTORS_REGISTRY
from app.services.market_data import get_price_matrix, get_quote_details
from app.services.stock_news import get_stock_news

router = APIRouter(prefix="/api/screener", tags=["screener"])


def _name_for_ticker(ticker: str) -> str | None:
    for sec in SECTORS_REGISTRY.values():
        for c in sec["covered"] + sec["roster"]:
            if c["ticker"].upper() == ticker.upper():
                return c["name"]
    return None


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else None


def _fundamentals(company: dict, sector_id: str) -> dict:
    """Normalise the hand-researched quarterly + fundamental fields (which differ per sector
    schema) into one common shape for the 'what to watch' briefing. Covered names carry these;
    roster names return has_results=False. Pure fact passthrough — no scoring, no advice."""
    f = {
        "has_results": False,
        "market_cap_cr": company.get("market_cap_cr"),
        "pe_label": company.get("pe_label"),
        "pat_yoy_pct": company.get("pat_yoy_pct"),
        "pat_yoy_label": company.get("pat_yoy_label"),
        "rev_growth_label": None, "rev_growth_pct": None,
        "margin_label": None, "margin_pct": None,
        "quality_label": None, "quality_value": None, "quality_status": None,
        "note": company.get("note"),
    }
    # Revenue growth (banks report NII instead of revenue).
    if sector_id == "banks":
        f["rev_growth_label"], f["rev_growth_pct"] = "NII YoY", company.get("nii_yoy_pct")
        f["margin_label"], f["margin_pct"] = "NIM", company.get("nim_pct")
        f["quality_label"], f["quality_value"] = "GNPA", company.get("gnpa_pct")
    elif sector_id == "it":
        f["rev_growth_label"], f["rev_growth_pct"] = "Revenue YoY", company.get("revenue_yoy_pct")
        f["margin_label"], f["margin_pct"] = "EBIT margin", company.get("ebit_margin_pct")
    else:  # hotels, auto
        f["rev_growth_label"], f["rev_growth_pct"] = "Revenue YoY", company.get("revenue_yoy_pct")
        f["margin_label"], f["margin_pct"] = "EBITDA margin", company.get("ebitda_margin_pct")
        f["quality_label"] = "Leverage"
        f["quality_value"] = company.get("leverage_label")
        f["quality_status"] = company.get("leverage_status")

    # "Has results" = we actually researched a P&L for this name (covered, not roster-only).
    if any(f[k] is not None for k in ("pat_yoy_pct", "rev_growth_pct", "margin_pct")):
        f["has_results"] = True
    return f


@router.get("")
async def screener():
    """Ranked technical snapshot across all covered sectors.

    Returns every stock with: momentum (1D/1W/1M/1Y %), RSI(14), volume, distance from
    the 52-week high, relative strength (its 1W% minus its sector's average 1W%), and a
    transparent composite momentum score. Also returns per-sector averages so the UI can
    show sector-wise strength. No advice, no price targets — screening data only.
    """
    # Collect the full universe with names + exchanges + fundamentals, tagged by sector.
    universe: list[dict] = []
    for sector_id, sec in SECTORS_REGISTRY.items():
        for c in sec["covered"] + sec["roster"]:
            universe.append({"sector": sector_id, "ticker": c["ticker"],
                             "name": c["name"], "exchange": c.get("exchange", "NSE"),
                             "fundamentals": _fundamentals(c, sector_id)})

    tickers = [u["ticker"] for u in universe]
    exchanges = {u["ticker"]: u["exchange"] for u in universe}

    # Two data pulls, both cached in market_data: momentum/RSI matrix + live quote (volume).
    matrix = get_price_matrix(tickers, exchanges)
    quotes = get_quote_details(tickers, exchanges)

    # Per-sector average 1W% (over stocks that actually have a value) → relative strength.
    sector_w1: dict[str, list[float]] = {}
    for u in universe:
        m = matrix.get(u["ticker"], {})
        if m.get("w1") is not None:
            sector_w1.setdefault(u["sector"], []).append(m["w1"])
    sector_w1_avg = {s: (sum(v) / len(v)) for s, v in sector_w1.items() if v}

    stocks: list[dict] = []
    for u in universe:
        m = matrix.get(u["ticker"], {})
        q = quotes.get(u["ticker"], {})
        price = m.get("price")
        if price is None:
            continue  # skip names with no live/among-history price (e.g. delisted symbols)

        w1 = m.get("w1")
        m1 = m.get("m1")
        rsi = m.get("rsi")
        rel = (w1 - sector_w1_avg[u["sector"]]) if (w1 is not None and u["sector"] in sector_w1_avg) else None

        # Transparent composite momentum score. Weighted blend of short-term momentum and
        # relative strength, with a small RSI adjustment that rewards a healthy uptrend zone
        # (50–65) and penalises overbought (>75) / weak (<40) — NOT a recommendation, just a
        # single sortable number. Every input is shown alongside so the user can judge.
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
            "sector": u["sector"],
            "ticker": u["ticker"],
            "name": u["name"],
            "price": price,
            "d1": m.get("d1"),
            "w1": w1,
            "m1": m1,
            "y1": m.get("y1"),
            "from_52w_high": m.get("from_52w_high"),
            "rsi": rsi,
            "volume": q.get("volume"),
            "rel_strength": _round(rel),
            "score": _round(score),
            "fundamentals": u["fundamentals"],
        })

    # Rank-wise: highest composite score first (None scores sink to the bottom).
    stocks.sort(key=lambda s: (s["score"] is not None, s["score"] if s["score"] is not None else 0),
                reverse=True)
    for i, s in enumerate(stocks, 1):
        s["rank"] = i

    return {
        "data": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": len(stocks),
            "stocks": stocks,
            "sectors": {s: _round(v) for s, v in sector_w1_avg.items()},
        }
    }


@router.get("/news/{ticker}")
async def stock_news(ticker: str):
    """Recent news headlines for one covered stock (Google News RSS, cached).

    Context only: returns headline + source + date + link (+ factual keyword tags found in
    the headline). It does NOT claim why a stock moved — the user reads the headlines and
    judges. 404 only if the ticker isn't in the covered universe.
    """
    name = _name_for_ticker(ticker)
    if not name:
        raise HTTPException(status_code=404, detail=f"Ticker '{ticker}' not in covered universe")
    return {"data": get_stock_news(name, ticker.upper())}
