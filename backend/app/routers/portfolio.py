"""Portfolio analytics routes (read-only, derived)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import TagCreate, TagUpdate, TradeNoteUpdate, TradeTagsUpdate
from app.services import analytics
from app.store import get_store

router = APIRouter(prefix="/api/clients", tags=["portfolio"])


async def _trades_or_404(client_id: str) -> list[dict]:
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return await store.list_trades(client_id)


@router.get("/{client_id}/portfolio")
async def portfolio(client_id: str):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.portfolio_summary(trades)}


@router.get("/{client_id}/holdings")
async def holdings(client_id: str):
    trades = await _trades_or_404(client_id)
    data = analytics.build_holdings(trades)
    data.pop("_positions", None)
    return {"data": data}


@router.get("/{client_id}/allocation")
async def allocation(
    client_id: str,
    by: str = Query("sector", pattern="^(sector|asset|stock|cap)$"),
    basis: str = Query("current", pattern="^(current|invested)$"),
):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.allocation(trades, by, basis)}


@router.get("/{client_id}/concentration")
async def concentration(client_id: str):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.concentration(trades)}


@router.get("/{client_id}/performance")
async def performance(client_id: str):
    trades = await _trades_or_404(client_id)
    return {"data": analytics.performance_series(trades)}


@router.get("/{client_id}/trades")
async def trades(
    client_id: str,
    symbol: str | None = None,
    trade_type: str | None = None,
    tag: str | None = None,
):
    store = get_store()
    ts = await _trades_or_404(client_id)
    if symbol:
        ts = [t for t in ts if t["symbol"] == symbol.upper()]
    if trade_type:
        ts = [t for t in ts if t["trade_type"] == trade_type.lower()]
    ts.sort(key=lambda t: (t["trade_date"], t.get("order_execution_time", "")), reverse=True)
    journal = await store.get_trade_journal(client_id)
    for t in ts:
        j = journal.get(t["fingerprint"], {})
        t["tag_ids"] = j.get("tag_ids", [])
        t["note"] = j.get("note", "")
    if tag:
        ts = [t for t in ts if tag in t["tag_ids"]]
    return {"data": ts, "meta": {"total": len(ts)}}


@router.get("/{client_id}/tags")
async def list_tags(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.list_tags(client_id)}


@router.post("/{client_id}/tags")
async def create_tag(client_id: str, body: TagCreate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    doc = {**body.model_dump(), "client_id": client_id}
    return {"data": await store.create_tag(doc)}


@router.patch("/{client_id}/tags/{tag_id}")
async def update_tag(client_id: str, tag_id: str, body: TagUpdate):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await store.update_tag(client_id, tag_id, patch)
    if not updated:
        raise HTTPException(404, "tag not found")
    return {"data": updated}


@router.delete("/{client_id}/tags/{tag_id}")
async def delete_tag(client_id: str, tag_id: str):
    store = get_store()
    ok = await store.delete_tag(client_id, tag_id)
    if not ok:
        raise HTTPException(404, "tag not found")
    return {"data": {"deleted": True}}


@router.patch("/{client_id}/trades/{fingerprint}/tags")
async def set_trade_tags(client_id: str, fingerprint: str, body: TradeTagsUpdate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.set_trade_tags(client_id, fingerprint, body.tag_ids)}


@router.patch("/{client_id}/trades/{fingerprint}/note")
async def set_trade_note(client_id: str, fingerprint: str, body: TradeNoteUpdate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": await store.set_trade_note(client_id, fingerprint, body.note)}


@router.get("/{client_id}/stocks/{symbol}")
async def stock(client_id: str, symbol: str):
    trades = await _trades_or_404(client_id)
    result = analytics.stock_analysis(trades, symbol)
    if result is None:
        raise HTTPException(404, "no trades for this symbol")
    return {"data": result}
