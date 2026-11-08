"""Research FastAPI router: Watchlists, Board, and Stock Theses."""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
import asyncpg

from pi_api.core.db import get_db_connection
from pi_api.modules.auth.deps import Principal, require_manager
from pi_api.modules.portfolio.service import PortfolioService
from pi_api.modules.research.schemas import (
    BoardItemCreate,
    BoardItemResponse,
    BoardItemUpdate,
    ScreenerSnapshotMeta,
    ScreenerSnapshotResponse,
    StockThesisCreate,
    StockThesisResponse,
    WatchlistCreate,
    WatchlistEntryAdd,
    WatchlistResponse,
)
from pi_api.modules.research.service import ResearchService

router = APIRouter(prefix="/research", tags=["research"], dependencies=[Depends(require_manager)])
service = ResearchService()
portfolio_service = PortfolioService()


async def _ensure_owner(conn: asyncpg.Connection, owner_id: Optional[UUID], principal: Principal) -> None:
    """Super-admin sees everything; a manager sees their own items and their clients' items."""
    if owner_id is None:
        raise HTTPException(status_code=404, detail="Not found.")
    if principal.role == "super_admin" or owner_id == principal.manager_id:
        return
    if await portfolio_service.validate_client_access(
        conn, owner_id, principal.role, principal.manager_id, principal.client_id
    ):
        return
    raise HTTPException(status_code=403, detail="Access forbidden.")


async def _ensure_client(conn: asyncpg.Connection, client_id: UUID, principal: Principal) -> None:
    if not await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    ):
        raise HTTPException(status_code=403, detail="Access to client forbidden.")


# --- Watchlists ---
@router.get("/watchlists", response_model=List[WatchlistResponse])
async def list_watchlists(
    owner_id: UUID = Query(...),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[WatchlistResponse]:
    """Lists all watchlists for a manager or client."""
    await _ensure_owner(conn, owner_id, principal)
    items = await service.list_watchlists(conn, owner_id)
    return [WatchlistResponse(**item) for item in items]


@router.post("/watchlists", response_model=WatchlistResponse)
async def create_watchlist(
    req: WatchlistCreate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> WatchlistResponse:
    """Creates a new watchlist."""
    await _ensure_owner(conn, req.owner_id, principal)
    item = await service.create_watchlist(conn, req.owner_type, req.owner_id, req.name, req.is_default)
    return WatchlistResponse(**item)


@router.post("/watchlists/{watchlist_id}/entries", status_code=204)
async def add_watchlist_entry(
    watchlist_id: UUID,
    entry: WatchlistEntryAdd,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Adds a symbol to a watchlist."""
    await _ensure_owner(conn, await service.get_watchlist_owner(conn, watchlist_id), principal)
    await service.add_watchlist_entry(
        conn,
        watchlist_id,
        entry.symbol,
        entry.added_price,
        entry.why,
        entry.remarks,
        entry.risks,
        entry.sector,
        entry.alert_price,
    )
    return Response(status_code=204)


@router.delete("/watchlists/{watchlist_id}/entries/{symbol}", status_code=204)
async def delete_watchlist_entry(
    watchlist_id: UUID,
    symbol: str,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Removes a symbol from a watchlist."""
    await _ensure_owner(conn, await service.get_watchlist_owner(conn, watchlist_id), principal)
    await service.delete_watchlist_entry(conn, watchlist_id, symbol)
    return Response(status_code=204)


# --- Kanban Board ---
@router.get("/board", response_model=List[BoardItemResponse])
async def list_board(
    owner_id: UUID = Query(...),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[BoardItemResponse]:
    """Lists all Kanban board items across lanes (watching, holding, exit)."""
    await _ensure_owner(conn, owner_id, principal)
    items = await service.list_board(conn, owner_id)
    return [BoardItemResponse(**item) for item in items]


@router.post("/board/items", response_model=BoardItemResponse)
async def create_board_item(
    item: BoardItemCreate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BoardItemResponse:
    """Adds a stock card to a board lane."""
    await _ensure_owner(conn, item.owner_id, principal)
    res = await service.create_board_item(
        conn,
        item.owner_type,
        item.owner_id,
        item.symbol,
        item.lane,
        item.entry_price,
        item.exit_price,
        item.why,
        item.colour,
        item.sort_order,
    )
    return BoardItemResponse(**res)


@router.patch("/board/items/{item_id}", response_model=BoardItemResponse)
async def update_board_item(
    item_id: UUID,
    item: BoardItemUpdate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> BoardItemResponse:
    """Updates card lane, prices, thesis, or sort order."""
    await _ensure_owner(conn, await service.get_board_item_owner(conn, item_id), principal)
    res = await service.update_board_item(
        conn,
        item_id,
        item.lane,
        item.entry_price,
        item.exit_price,
        item.why,
        item.colour,
        item.sort_order,
    )
    if not res:
        raise HTTPException(status_code=404, detail="Board item not found.")
    return BoardItemResponse(**res)


@router.delete("/board/items/{item_id}", status_code=204)
async def delete_board_item(
    item_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Deletes a card from the board."""
    await _ensure_owner(conn, await service.get_board_item_owner(conn, item_id), principal)
    await service.delete_board_item(conn, item_id)
    return Response(status_code=204)


# --- Stock Theses ---
@router.get("/theses/{client_id}/{symbol}", response_model=StockThesisResponse)
async def get_stock_thesis(
    client_id: UUID,
    symbol: str,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> StockThesisResponse:
    """Gets research thesis document for a symbol."""
    await _ensure_client(conn, client_id, principal)
    res = await service.get_thesis(conn, client_id, symbol)
    if not res:
        raise HTTPException(status_code=404, detail="No thesis found.")
    return StockThesisResponse(**res)


@router.put("/theses/{client_id}/{symbol}", response_model=StockThesisResponse)
async def save_stock_thesis(
    client_id: UUID,
    symbol: str,
    req: StockThesisCreate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> StockThesisResponse:
    """Upserts research thesis document for a symbol."""
    await _ensure_client(conn, client_id, principal)
    res = await service.save_thesis(conn, client_id, symbol, req.thesis)
    return StockThesisResponse(**res)


# --- Screener (read-only; research.screener_snapshots) ---
@router.get(
    "/screener/latest",
    response_model=ScreenerSnapshotResponse,
    dependencies=[Depends(require_manager)],
)
async def get_latest_screener(
    model: Optional[str] = Query(None),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ScreenerSnapshotResponse:
    """Latest screener snapshot, normalised; slicing (top-N, sector, sort) is client-side."""
    res = await service.get_latest_screener(conn, model)
    return ScreenerSnapshotResponse(**res)


@router.get(
    "/screener/snapshots",
    response_model=List[ScreenerSnapshotMeta],
    dependencies=[Depends(require_manager)],
)
async def list_screener_snapshots(
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[ScreenerSnapshotMeta]:
    """Lists available screener snapshots (as_of, model)."""
    items = await service.list_screener_snapshots(conn)
    return [ScreenerSnapshotMeta(**i) for i in items]
