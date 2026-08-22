"""Watchlists — manager-level and client-level. Live-priced. No auth in Phase 1."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.market_data import get_quote_details
from app.services.securities import classify
from app.store import get_store

router = APIRouter(prefix="/api", tags=["watchlists"])


class SymbolIn(BaseModel):
    symbol: str


def _priced(symbols: list[str]) -> list[dict]:
    if not symbols:
        return []
    quotes = get_quote_details(symbols)
    rows = []
    for s in symbols:
        q = quotes.get(s, {})
        meta = classify(s)
        rows.append(
            {
                "symbol": s,
                "price": q.get("price"),
                "change": q.get("change"),
                "change_pct": q.get("change_pct"),
                "sector": meta["sector"],
                "asset_class": meta["asset_class"],
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
    syms = await store.add_watchlist_symbol("MANAGER", manager_id, body.symbol)
    return {"data": _priced(syms)}


@router.delete("/managers/{manager_id}/watchlist/{symbol}")
async def remove_manager_symbol(manager_id: str, symbol: str):
    store = get_store()
    syms = await store.remove_watchlist_symbol("MANAGER", manager_id, symbol)
    return {"data": _priced(syms)}


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
    syms = await store.add_watchlist_symbol("CLIENT", client_id, body.symbol)
    return {"data": _priced(syms)}


@router.delete("/clients/{client_id}/watchlist/{symbol}")
async def remove_client_symbol(client_id: str, symbol: str):
    store = get_store()
    syms = await store.remove_watchlist_symbol("CLIENT", client_id, symbol)
    return {"data": _priced(syms)}
