"""Manager Kanban board ("MyBoard") — plan a trade idea before it's real.

Three columns: Watching -> Holding -> Exit. entry_price/exit_price are the plan,
set at add time and editable while the idea is still just an idea. The moment a
card crosses into Holding or Exit, the router stamps the actual live price into
entered_price/exited_price — so a card ends up carrying both what was planned and
what actually happened, without retyping anything.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.services import auth
from app.services.market_data import get_quote_details
from app.store import get_store

router = APIRouter(prefix="/api", tags=["board"])


class BoardStatus(str, Enum):
    WATCHING = "watching"
    HOLDING = "holding"
    EXIT = "exit"


class BoardItemAdd(BaseModel):
    symbol: str
    entry_price: float | None = None
    exit_price: float | None = None
    why: str | None = None


class BoardItemUpdate(BaseModel):
    entry_price: float | None = None
    exit_price: float | None = None
    why: str | None = None
    status: BoardStatus | None = None


def _priced(items: list[dict]) -> list[dict]:
    if not items:
        return []
    symbols = list({i["symbol"] for i in items})
    quotes = get_quote_details(symbols)
    rows = []
    for i in items:
        q = quotes.get(i["symbol"], {})
        rows.append({**i, "price": q.get("price"), "change_pct": q.get("change_pct")})
    return rows


@router.get("/managers/{manager_id}/board")
async def get_board(manager_id: str, _ws: auth.Identity = Depends(auth.require_manager_scope)):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    return {"data": _priced(await store.get_board_items("MANAGER", manager_id))}


@router.post("/managers/{manager_id}/board")
async def add_board_item(manager_id: str, body: BoardItemAdd, _ws: auth.Identity = Depends(auth.require_manager_scope)):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    items = await store.add_board_item(
        "MANAGER", manager_id, body.symbol.upper(),
        entry_price=body.entry_price, exit_price=body.exit_price, why=body.why,
    )
    return {"data": _priced(items)}


@router.patch("/managers/{manager_id}/board/{item_id}")
async def update_board_item(manager_id: str, item_id: str, body: BoardItemUpdate, _ws: auth.Identity = Depends(auth.require_manager_scope)):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")

    patch = body.model_dump(exclude_unset=True)
    if "status" in patch:
        patch["status"] = BoardStatus(patch["status"]).value
        items = await store.get_board_items("MANAGER", manager_id)
        item = next((i for i in items if i["id"] == item_id), None)
        price = get_quote_details([item["symbol"]]).get(item["symbol"], {}).get("price") if item else None
        if patch["status"] == BoardStatus.HOLDING.value:
            patch["entered_at"], patch["entered_price"] = date.today().isoformat(), price
        elif patch["status"] == BoardStatus.EXIT.value:
            patch["exited_at"], patch["exited_price"] = date.today().isoformat(), price

    items = await store.update_board_item("MANAGER", manager_id, item_id, patch)
    if items is None:
        raise HTTPException(404, "item not found")
    return {"data": _priced(items)}


@router.delete("/managers/{manager_id}/board/{item_id}")
async def remove_board_item(manager_id: str, item_id: str, _ws: auth.Identity = Depends(auth.require_manager_scope)):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    items = await store.remove_board_item("MANAGER", manager_id, item_id)
    return {"data": _priced(items)}
