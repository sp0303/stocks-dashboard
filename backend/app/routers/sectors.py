"""Sector research — polymorphic multi-sector intelligence.
Covers Hotels, Banking & Financial Institutions (BFSI), IT Services, and Automotive (OEMs).

Live market data (price, day change, day high/low, volume) comes dynamically via
app.services.market_data (Angel One SmartAPI with Yahoo Finance fallback).
Operating KPIs are researched quarterly snapshots.
Portfolio holdings cross-reference open positions from the connected client/Kite tradebook.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.data import (
    auto_sector, banking_sector, cement_sector, energy_sector, fmcg_sector,
    hotel_sector, it_sector, metals_sector, pharma_sector, realty_sector,
)
from app.services.engine import compute_positions, split_intraday
from app.services.market_data import get_price_matrix, get_quote_details
from app.store import get_store

router = APIRouter(prefix="/api/sectors", tags=["sectors"])

SECTORS_REGISTRY = {
    "hotels": {
        "covered": hotel_sector.HOTEL_COVERED,
        "roster": hotel_sector.HOTEL_ROSTER,
        "industry": hotel_sector.INDUSTRY_BENCHMARK,
        "tickers": hotel_sector.ALL_TICKERS,
        "exchanges": hotel_sector.EXCHANGES,
    },
    "banks": {
        "covered": banking_sector.BANKING_COVERED,
        "roster": banking_sector.BANKING_ROSTER,
        "industry": banking_sector.INDUSTRY_BENCHMARK,
        "tickers": banking_sector.ALL_TICKERS,
        "exchanges": banking_sector.EXCHANGES,
    },
    "it": {
        "covered": it_sector.IT_COVERED,
        "roster": it_sector.IT_ROSTER,
        "industry": it_sector.INDUSTRY_BENCHMARK,
        "tickers": it_sector.ALL_TICKERS,
        "exchanges": it_sector.EXCHANGES,
    },
    "auto": {
        "covered": auto_sector.AUTO_COVERED,
        "roster": auto_sector.AUTO_ROSTER,
        "industry": auto_sector.INDUSTRY_BENCHMARK,
        "tickers": auto_sector.ALL_TICKERS,
        "exchanges": auto_sector.EXCHANGES,
    },
    # ── Newer sectors: validated NSE rosters + domain-specific sub-industry labels.
    # Quarterly KPI values are pending research (see RESEARCH_TODO.md); live market data
    # (price/momentum/RSI/levels) works for these now.
    "pharma": {
        "covered": pharma_sector.PHARMA_COVERED,
        "roster": pharma_sector.PHARMA_ROSTER,
        "industry": pharma_sector.INDUSTRY_BENCHMARK,
        "tickers": pharma_sector.ALL_TICKERS,
        "exchanges": pharma_sector.EXCHANGES,
    },
    "fmcg": {
        "covered": fmcg_sector.FMCG_COVERED,
        "roster": fmcg_sector.FMCG_ROSTER,
        "industry": fmcg_sector.INDUSTRY_BENCHMARK,
        "tickers": fmcg_sector.ALL_TICKERS,
        "exchanges": fmcg_sector.EXCHANGES,
    },
    "metals": {
        "covered": metals_sector.METALS_COVERED,
        "roster": metals_sector.METALS_ROSTER,
        "industry": metals_sector.INDUSTRY_BENCHMARK,
        "tickers": metals_sector.ALL_TICKERS,
        "exchanges": metals_sector.EXCHANGES,
    },
    "energy": {
        "covered": energy_sector.ENERGY_COVERED,
        "roster": energy_sector.ENERGY_ROSTER,
        "industry": energy_sector.INDUSTRY_BENCHMARK,
        "tickers": energy_sector.ALL_TICKERS,
        "exchanges": energy_sector.EXCHANGES,
    },
    "realty": {
        "covered": realty_sector.REALTY_COVERED,
        "roster": realty_sector.REALTY_ROSTER,
        "industry": realty_sector.INDUSTRY_BENCHMARK,
        "tickers": realty_sector.ALL_TICKERS,
        "exchanges": realty_sector.EXCHANGES,
    },
    "cement": {
        "covered": cement_sector.CEMENT_COVERED,
        "roster": cement_sector.CEMENT_ROSTER,
        "industry": cement_sector.INDUSTRY_BENCHMARK,
        "tickers": cement_sector.ALL_TICKERS,
        "exchanges": cement_sector.EXCHANGES,
    },
}


async def _get_held_positions_map() -> dict[str, dict]:
    """Returns {SYMBOL: {"quantity": int, "avg_cost": float}} for currently held open positions
    across the active client tradebook/portfolio."""
    try:
        store = get_store()
        clients = await store.list_clients()
        held_map: dict[str, dict] = {}
        for client in clients:
            raw_trades = await store.list_trades(client["id"])
            if not raw_trades:
                continue
            delivery, _ = split_intraday(raw_trades)
            if not delivery:
                continue
            positions, _ = compute_positions(delivery)
            for pos in positions:
                if pos.get("quantity", 0) > 0:
                    sym = pos["symbol"]
                    held_map[sym] = {
                        "quantity": pos.get("quantity", 0),
                        "avg_cost": pos.get("avg_cost", 0.0),
                    }
        return held_map
    except Exception:
        return {}


async def _build_sector_response(sector_id: str) -> dict:
    sec = SECTORS_REGISTRY.get(sector_id)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Sector '{sector_id}' not found")

    tickers = sec["tickers"]
    exchanges = sec["exchanges"]
    quotes = get_quote_details(tickers, exchanges)
    held_map = await _get_held_positions_map()

    def with_market_and_portfolio(company: dict) -> dict:
        sym = company["ticker"]
        q = quotes.get(sym, {})
        holding = held_map.get(sym)
        is_held = holding is not None
        return {
            **company,
            "price": q.get("price"),
            "change": q.get("change"),
            "change_pct": q.get("change_pct"),
            "volume": q.get("volume"),
            "day_high": q.get("day_high"),
            "day_low": q.get("day_low"),
            "prev_close": q.get("prev_close"),
            "is_held": is_held,
            "holding_qty": holding["quantity"] if is_held else None,
            "avg_cost": holding["avg_cost"] if is_held else None,
        }

    return {
        "data": {
            "sector": sector_id,
            "industry": sec["industry"],
            "covered": [with_market_and_portfolio(c) for c in sec["covered"]],
            "roster": [with_market_and_portfolio(c) for c in sec["roster"]],
        }
    }


async def _build_price_matrix_response(sector_id: str) -> dict:
    sec = SECTORS_REGISTRY.get(sector_id)
    if not sec:
        raise HTTPException(status_code=404, detail=f"Sector '{sector_id}' not found")

    tickers = sec["tickers"]
    exchanges = sec["exchanges"]
    names = {c["ticker"]: c["name"] for c in sec["covered"] + sec["roster"]}
    matrix = get_price_matrix(tickers, exchanges)

    return {
        "data": [
            {"ticker": t, "name": names.get(t, t), **matrix.get(t, {})}
            for t in tickers
        ]
    }


# Backwards compatibility endpoints
@router.get("/hotels")
async def hotels_sector():
    return await _build_sector_response("hotels")


@router.get("/hotels/price-matrix")
async def hotels_price_matrix():
    return await _build_price_matrix_response("hotels")


# Generic polymorphic endpoints
@router.get("/{sector_id}")
async def get_sector(sector_id: str):
    return await _build_sector_response(sector_id.lower())


@router.get("/{sector_id}/price-matrix")
async def get_sector_price_matrix(sector_id: str):
    return await _build_price_matrix_response(sector_id.lower())
