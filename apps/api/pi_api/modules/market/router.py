"""Market FastAPI router."""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
import asyncpg

from pi_api.core.db import get_db_connection
from pi_api.modules.market.schemas import (
    BenchmarkHealthItem,
    BenchmarkSeriesPointResponse,
    CalendarDayResponse,
    LatestCloseItem,
    QuoteResponse,
    SecuritySearchItem,
)
from pi_api.modules.market.service import MarketService

router = APIRouter(prefix="/market", tags=["market"])
service = MarketService()


@router.get("/securities/search", response_model=List[SecuritySearchItem])
async def search_securities(
    q: str = Query(..., min_length=1),
    limit: int = Query(20, le=100),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[SecuritySearchItem]:
    """Searches securities master by symbol or name."""
    items = await service.search_securities(conn, q, limit)
    return [SecuritySearchItem(**item) for item in items]


@router.get("/closes", response_model=List[LatestCloseItem])
async def get_latest_closes(
    symbols: str = Query(..., description="Comma-separated symbols, max 200"),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[LatestCloseItem]:
    """Latest stored daily close per symbol (precomputed EOD; no provider call). Unpriced = absent."""
    rows = await service.get_latest_closes(conn, symbols.split(","))
    return [LatestCloseItem(**r) for r in rows]


@router.get("/quotes/{exchange}/{symbol}", response_model=QuoteResponse)
async def get_quote(
    exchange: str,
    symbol: str,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> QuoteResponse:
    """Returns price quote keyed strictly on (exchange, symbol) with staleness flag (Rule R6)."""
    quote = await service.get_quote(conn, symbol, exchange)
    if not quote:
        raise HTTPException(status_code=404, detail=f"No price found for {exchange}:{symbol}")
    return QuoteResponse(**quote)


@router.get("/calendar", response_model=List[CalendarDayResponse])
async def get_trading_calendar(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[CalendarDayResponse]:
    """Returns trading calendar days and market open/close sessions."""
    s_date = start_date or (date.today() - timedelta(days=30))
    e_date = end_date or (date.today() + timedelta(days=30))
    items = await service.get_calendar(conn, s_date, e_date)
    return [CalendarDayResponse(**item) for item in items]


@router.get("/benchmarks/health", response_model=List[BenchmarkHealthItem])
async def get_benchmark_health(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[BenchmarkHealthItem]:
    """Monitors benchmark freshness and sounds alarm if stale > 2 sessions (Rule R10)."""
    items = await service.get_benchmark_health(conn)
    return [BenchmarkHealthItem(**item) for item in items]


@router.get("/benchmarks/{code}/series", response_model=List[BenchmarkSeriesPointResponse])
async def get_benchmark_series(
    code: str,
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[BenchmarkSeriesPointResponse]:
    """Returns daily historical values for a benchmark index (Rule R10)."""
    items = await service.get_benchmark_series(conn, code.upper(), start_date, end_date)
    return [BenchmarkSeriesPointResponse(**item) for item in items]

