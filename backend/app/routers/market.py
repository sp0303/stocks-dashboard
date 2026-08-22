"""Market data routes: historical price series for charts."""
from __future__ import annotations

from fastapi import APIRouter, Query

from app.services.market_data import get_history

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/history/{symbol}")
async def history(
    symbol: str,
    from_date: str | None = Query(None, alias="from", description="YYYY-MM-DD"),
    interval: str = Query("1d", pattern="^(1d|1wk|1mo)$"),
    exchange: str = "NSE",
):
    return {"data": get_history(symbol.upper(), from_date, interval, exchange)}
