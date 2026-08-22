"""Watchlists — manager-level and client-level. Live-priced. No auth in Phase 1.

Each entry can carry an optional "checkpoint" date — the date a manager/client
started watching the stock (or a decision date) — so the list can show what
the stock has done since that day, alongside today's live price.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.market_data import get_checkpoint_prices, get_quote_details
from app.services.securities import classify
from app.store import get_store

router = APIRouter(prefix="/api", tags=["watchlists"])


class SymbolIn(BaseModel):
    symbol: str
    checkpoint_date: str | None = None  # YYYY-MM-DD


class CheckpointIn(BaseModel):
    checkpoint_date: str | None = None  # YYYY-MM-DD; null clears it


def _priced(entries: list[dict]) -> list[dict]:
    if not entries:
        return []
    symbols = [e["symbol"] for e in entries]
    quotes = get_quote_details(symbols)

    checkpoint_pairs = [(e["symbol"], e["checkpoint_date"]) for e in entries if e.get("checkpoint_date")]
    checkpoint_prices = get_checkpoint_prices(checkpoint_pairs)

    rows = []
    for e in entries:
        s = e["symbol"]
        q = quotes.get(s, {})
        meta = classify(s)
        cp_date = e.get("checkpoint_date")
        cp_price = checkpoint_prices.get(s)
        cp_change_pct = None
        if cp_price and q.get("price") is not None:
            cp_change_pct = round((q["price"] - cp_price) / cp_price * 100, 2)
        rows.append(
            {
                "symbol": s,
                "price": q.get("price"),
                "change": q.get("change"),
                "change_pct": q.get("change_pct"),
                "sector": meta["sector"],
                "asset_class": meta["asset_class"],
                "checkpoint_date": cp_date,
                "checkpoint_price": cp_price,
                "checkpoint_change_pct": cp_change_pct,
            }
        )
    return rows


# ── Manager watchlist ──────────────────────────────────────────────
@router.get("/managers/{manager_id}/watchlist")
async def get_manager_watchlist(manager_id: str):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    return {"data": _priced(await store.get_watchlist("MANAGER", manager_id))}


@router.post("/managers/{manager_id}/watchlist")
async def add_manager_symbol(manager_id: str, body: SymbolIn):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    entries = await store.add_watchlist_symbol("MANAGER", manager_id, body.symbol, body.checkpoint_date)
    return {"data": _priced(entries)}


@router.patch("/managers/{manager_id}/watchlist/{symbol}/checkpoint")
async def set_manager_checkpoint(manager_id: str, symbol: str, body: CheckpointIn):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    entries = await store.set_watchlist_checkpoint("MANAGER", manager_id, symbol.upper(), body.checkpoint_date)
    return {"data": _priced(entries)}


@router.delete("/managers/{manager_id}/watchlist/{symbol}")
async def remove_manager_symbol(manager_id: str, symbol: str):
    store = get_store()
    entries = await store.remove_watchlist_symbol("MANAGER", manager_id, symbol)
    return {"data": _priced(entries)}


# ── Client watchlist ───────────────────────────────────────────────
@router.get("/clients/{client_id}/watchlist")
async def get_client_watchlist(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    return {"data": _priced(await store.get_watchlist("CLIENT", client_id))}


@router.post("/clients/{client_id}/watchlist")
async def add_client_symbol(client_id: str, body: SymbolIn):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    entries = await store.add_watchlist_symbol("CLIENT", client_id, body.symbol, body.checkpoint_date)
    return {"data": _priced(entries)}


@router.patch("/clients/{client_id}/watchlist/{symbol}/checkpoint")
async def set_client_checkpoint(client_id: str, symbol: str, body: CheckpointIn):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    entries = await store.set_watchlist_checkpoint("CLIENT", client_id, symbol.upper(), body.checkpoint_date)
    return {"data": _priced(entries)}


@router.delete("/clients/{client_id}/watchlist/{symbol}")
async def remove_client_symbol(client_id: str, symbol: str):
    store = get_store()
    entries = await store.remove_watchlist_symbol("CLIENT", client_id, symbol)
    return {"data": _priced(entries)}
