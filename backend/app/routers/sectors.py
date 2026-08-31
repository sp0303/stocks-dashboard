"""Sector research — hotel/hospitality sector overview.

Live price comes from the same Yahoo Finance provider used everywhere else in the app
(market_data.get_quote_details). Operating KPIs (occupancy/ARR/RevPAR/etc.) are static,
hand-researched data — see app/data/hotel_sector.py for why and what's next.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.data.hotel_sector import ALL_TICKERS, EXCHANGES, HOTEL_COVERED, HOTEL_ROSTER, INDUSTRY_BENCHMARK
from app.services.market_data import get_price_matrix, get_quote_details

router = APIRouter(prefix="/api/sectors", tags=["sectors"])

_NAMES = {c["ticker"]: c["name"] for c in HOTEL_COVERED + HOTEL_ROSTER}


@router.get("/hotels")
async def hotels_sector():
    quotes = get_quote_details(ALL_TICKERS, EXCHANGES)

    def with_quote(company: dict) -> dict:
        q = quotes.get(company["ticker"], {})
        return {
            **company,
            "price": q.get("price"),
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "volume": q.get("volume"),
            "day_high": q.get("day_high"),
            "day_low": q.get("day_low"),
            "prev_close": q.get("prev_close"),
        }

    return {
        "data": {
            "industry": INDUSTRY_BENCHMARK,
            "covered": [with_quote(c) for c in HOTEL_COVERED],
            "roster": [with_quote(c) for c in HOTEL_ROSTER],
        }
    }


@router.get("/hotels/price-matrix")
async def hotels_price_matrix():
    """1D/1W/1M/1Y momentum + % off 52-week high — derived from daily OHLC history
    (Yahoo Finance, same feed as the rest of the app), not quarterly fundamentals."""
    matrix = get_price_matrix(ALL_TICKERS, EXCHANGES)
    return {
        "data": [
            {"ticker": t, "name": _NAMES.get(t, t), **matrix.get(t, {})}
            for t in ALL_TICKERS
        ]
    }
