"""Ledger FastAPI router."""

from __future__ import annotations

from datetime import date
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
import asyncpg

from pi_api.core.db import get_db_connection
from pi_api.modules.auth.deps import Principal, require_manager
from pi_api.modules.ledger.schemas import (
    CorporateActionItemResponse,
    DividendCreate,
    DividendItemResponse,
    DividendSuggestion,
    ManualTradeCreate,
    ManualTradeResult,
    TradeItemResponse,
    TradeVoidResult,
    UploadRejectItem,
    UploadResponse,
)
from pi_api.modules.ledger.service import LedgerService
from pi_api.modules.portfolio.service import PortfolioService
from pi_workers.ingest_worker import ingest_tradebook
from pi_workers.portfolio_worker import recompute_single_client

router = APIRouter(prefix="/ledger", tags=["ledger"], dependencies=[Depends(require_manager)])
service = LedgerService()
portfolio_service = PortfolioService()


@router.get("/trades", response_model=List[TradeItemResponse])
async def list_trades(
    client_id: UUID = Query(...),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[TradeItemResponse]:
    """Lists trades for a given client with tenant check and filtering."""
    allowed = await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client trades forbidden.")

    items = await service.list_trades_by_side(conn, client_id, symbol, side, start_date, end_date, limit, offset)
    return [TradeItemResponse(**item) for item in items]


@router.get("/manager-trades", response_model=List[TradeItemResponse])
async def list_manager_trades(
    manager_id: Optional[UUID] = Query(None),
    symbol: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[TradeItemResponse]:
    """Lists trades across all clients managed by the authenticated manager."""
    eff_manager_id = principal.manager_id if principal.role == "manager" else (manager_id or principal.manager_id)
    if not eff_manager_id:
        raise HTTPException(status_code=400, detail="manager_id is required.")

    items = await service.list_manager_trades(
        conn, eff_manager_id, client_id=None, symbol=symbol, side=side,
        start_date=start_date, end_date=end_date, limit=limit, offset=offset
    )
    return [TradeItemResponse(**item) for item in items]



@router.get("/corporate-actions", response_model=List[CorporateActionItemResponse])
async def list_corporate_actions(
    symbol: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0, ge=0),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[CorporateActionItemResponse]:
    """Lists corporate actions (splits, bonuses, dividends, demergers) from ledger."""
    items = await service.list_corporate_actions(
        conn, symbol=symbol, action_type=type, start_date=start_date,
        end_date=end_date, limit=limit, offset=offset
    )
    return [CorporateActionItemResponse(**item) for item in items]



@router.get("/uploads", response_model=List[UploadResponse])
async def list_uploads(
    client_id: UUID = Query(...),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[UploadResponse]:
    """Lists upload history for a client."""
    items = await service.list_uploads(conn, client_id)
    return [UploadResponse(**item) for item in items]


@router.get("/uploads/{upload_id}/rejects", response_model=List[UploadRejectItem])
async def get_upload_rejects(
    upload_id: UUID,
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[UploadRejectItem]:
    """Returns rejected rows report with exact reasons (Rule R13)."""
    items = await service.get_rejects(conn, upload_id)
    return [UploadRejectItem(**item) for item in items]


@router.post("/upload")
async def upload_tradebook(
    client_id: UUID = Form(...),
    broker_format: str = Form("ZERODHA"),
    file: UploadFile = File(...),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Uploads and ingests broker tradebook CSV with tenant check (Rule R13)."""
    allowed = await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Cannot upload tradebook for this client.")

    file_bytes = await file.read()
    result = await ingest_tradebook(client_id, file.filename or "tradebook.csv", file_bytes, broker_format)
    return result


@router.get("/export/{client_id}")
async def export_tradebook(
    client_id: UUID,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
):
    """Downloads lossless, round-trippable tradebook CSV adhering to Rule R14 with tenant check."""
    allowed = await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Cannot export tradebook for this client.")

    csv_content = await service.generate_export_csv(conn, client_id)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=tradebook_{client_id}_{date.today()}.csv"
        },
    )


async def _ensure_access(conn: asyncpg.Connection, client_id: UUID, principal: Principal) -> None:
    allowed = await portfolio_service.validate_client_access(
        conn, client_id, principal.role, principal.manager_id, principal.client_id
    )
    if not allowed:
        raise HTTPException(status_code=403, detail="Access to client forbidden.")


# --- Dividends ---
@router.get("/dividends", response_model=List[DividendItemResponse])
async def list_dividends(
    client_id: UUID = Query(...),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[DividendItemResponse]:
    """Lists dividends received by a client (ledger.dividends)."""
    await _ensure_access(conn, client_id, principal)
    items = await service.list_dividends(conn, client_id)
    return [DividendItemResponse(**item) for item in items]


@router.get("/dividends/suggestions", response_model=List[DividendSuggestion])
async def suggest_dividends(
    client_id: UUID = Query(...),
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[DividendSuggestion]:
    """'Find missing dividends': stored DIVIDEND actions held on their ex-date and not yet
    recorded. Read-only; accepting a row posts it to POST /ledger/dividends."""
    await _ensure_access(conn, client_id, principal)
    items = await service.suggest_dividends(conn, client_id)
    return [DividendSuggestion(**i) for i in items]


@router.post("/dividends", response_model=DividendItemResponse, status_code=201)
async def add_dividend(
    req: DividendCreate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> DividendItemResponse:
    """Records a manual dividend (source='manual')."""
    await _ensure_access(conn, req.client_id, principal)
    item = await service.add_dividend(conn, req.model_dump())
    return DividendItemResponse(**item)


@router.delete("/dividends/{dividend_id}", status_code=204)
async def delete_dividend(
    dividend_id: int,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> Response:
    """Deletes a manually entered dividend. Provider-sourced rows cannot be deleted."""
    owner = await service.get_dividend_owner(conn, dividend_id)
    if not owner:
        raise HTTPException(status_code=404, detail="Dividend not found.")
    await _ensure_access(conn, owner["client_id"], principal)
    if owner["source"] != "manual":
        raise HTTPException(status_code=409, detail="Only manual dividends can be deleted.")
    await service.delete_dividend(conn, dividend_id)
    return Response(status_code=204)


# --- Manual trades (Rule R13: append-only; void sets deleted_at) ---
@router.post("/trades/manual", response_model=ManualTradeResult, status_code=201)
async def add_manual_trade(
    req: ManualTradeCreate,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> ManualTradeResult:
    """Records a manual trade and recomputes the client's portfolio."""
    await _ensure_access(conn, req.client_id, principal)
    res = await service.add_manual_trade(conn, req.model_dump(), recompute_single_client)
    return ManualTradeResult(**res)


@router.delete("/trades/{trade_id}", response_model=TradeVoidResult)
async def void_manual_trade(
    trade_id: int,
    principal: Principal = Depends(require_manager),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> TradeVoidResult:
    """Voids a manual trade (soft delete via deleted_at). Broker trades cannot be voided."""
    owner = await service.get_trade_owner(conn, trade_id)
    if not owner or owner["deleted_at"] is not None:
        raise HTTPException(status_code=404, detail="Trade not found.")
    await _ensure_access(conn, owner["client_id"], principal)
    if owner["source"] != "manual":
        raise HTTPException(status_code=409, detail="Only manual trades can be deleted.")
    res = await service.void_manual_trade(conn, trade_id, owner["client_id"], recompute_single_client)
    return TradeVoidResult(**res)
