"""Ledger schemas adhering to Rules R13, R14, R15."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TradeItemResponse(BaseModel):
    trade_id: int
    client_id: UUID
    client_name: Optional[str] = None
    client_code: Optional[str] = None
    symbol: str
    exchange: str
    trade_date: date
    trade_type: str
    quantity: float
    price: float
    trade_value: float
    charges: Optional[float] = None
    charges_known: bool = False
    segment: str = "EQ"
    broker_trade_id: Optional[str] = None
    broker_order_id: Optional[str] = None
    source: str
    created_at: datetime


class UploadResponse(BaseModel):
    upload_id: UUID
    client_id: UUID
    file_name: str
    broker_format: str
    rows_total: int
    rows_imported: int
    rows_duplicate: int
    rows_rejected: int
    status: str
    uploaded_at: datetime


class UploadRejectItem(BaseModel):
    upload_id: UUID
    row_no: int
    reason: str
    raw: Dict[str, Any]


class CorporateActionItemResponse(BaseModel):
    action_id: int
    key: str
    symbol: str
    isin: Optional[str] = None
    ex_date: date
    type: str
    qty_multiplier: Optional[float] = None
    amount_per_share: Optional[float] = None
    subject: Optional[str] = None
    source: str = "NSE"
    fetched_at: datetime



class DividendItemResponse(BaseModel):
    dividend_id: int
    client_id: UUID
    symbol: str
    ex_date: date
    amount_per_share: float
    quantity: float
    amount: float
    source: str


class DividendSuggestion(BaseModel):
    """A proposed dividend from a stored corporate action; not recorded until accepted."""

    symbol: str
    ex_date: date
    amount_per_share: float
    estimated_quantity: float
    estimated_total: float
    subject: Optional[str] = None
    source: Optional[str] = None


class DividendCreate(BaseModel):
    client_id: UUID
    symbol: str = Field(..., min_length=1, max_length=32)
    ex_date: date
    amount_per_share: float = Field(..., gt=0)
    quantity: float = Field(..., gt=0)


class ManualTradeCreate(BaseModel):
    """Manual trade entry (source='manual', Rule R13: append-only, voided not deleted)."""

    client_id: UUID
    symbol: str = Field(..., min_length=1, max_length=32)
    exchange: Literal["NSE", "BSE"] = "NSE"
    trade_date: date
    trade_type: Literal["buy", "sell"]
    quantity: float = Field(..., gt=0)
    price: float = Field(..., ge=0)
    note: Optional[str] = Field(None, max_length=500)
    idempotency_key: Optional[str] = Field(None, min_length=8, max_length=64)


class ManualTradeResult(BaseModel):
    trade_id: Optional[int] = None
    created: bool
    recomputed: bool


class TradeVoidResult(BaseModel):
    trade_id: int
    voided: bool
    recomputed: bool
