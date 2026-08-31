"""Watchlists — manager-level and client-level. Live-priced. No auth in Phase 1.

Each entry tracks not just the symbol but why it was added, its price at add time,
and an optional future alert date — added_price/added_date are captured once and
never re-derived; why/alert_date are editable via PATCH.
"""
from __future__ import annotations

import asyncio
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services.alerts import check_and_send, check_owner
from app.services.mailer import MailNotConfigured, send_email
from app.services.market_data import get_history, get_quote_details
from app.services.securities import classify
from app.store import get_store

router = APIRouter(prefix="/api", tags=["watchlists"])


class WatchlistAdd(BaseModel):
    symbol: str
    why: str | None = None
    alert_date: str | None = None
    alert_price: float | None = None  # target/trigger price
    added_date: str | None = None  # defaults to today if omitted
    remarks: str | None = None
    risks: str | None = None
    sector: str | None = None  # manual override of the classifier's guess


class WatchlistEntryUpdate(BaseModel):
    why: str | None = None
    alert_date: str | None = None
    alert_price: float | None = None
    added_date: str | None = None
    added_price: float | None = None
    remarks: str | None = None
    risks: str | None = None
    sector: str | None = None


class WatchlistMeta(BaseModel):
    name: str


MAX_WATCHLISTS = 10  # per owner (managers can create up to this many named lists)


def _resolve_added_price(symbol: str, added_date: str | None) -> float | None:
    """Today (or no date given) -> live quote. A back-date -> that day's closing
    price from history (nearest close on/after the date, since exchanges are
    closed on weekends/holidays)."""
    if not added_date or added_date == date.today().isoformat():
        return get_quote_details([symbol]).get(symbol, {}).get("price")
    hist = get_history(symbol, from_date=added_date)
    points = hist.get("points", [])
    if not points:
        return None
    for p in points:
        if p["date"] >= added_date:
            return p["close"]
    return points[-1]["close"]


async def _backfill_added_prices(store, owner_type: str, owner_id: str, entries: list[dict],
                                 watchlist_id: str | None = None) -> list[dict]:
    """Entries created before added_price existed (or whose live/history fetch
    failed at add time) have added_date but no added_price. Resolve it once here
    and persist so it's never re-fetched — same caching principle as dividends."""
    for e in entries:
        if e.get("added_price") is None and e.get("added_date"):
            price = _resolve_added_price(e["symbol"], e["added_date"])
            if price is not None:
                e["added_price"] = price
                await store.update_watchlist_entry(owner_type, owner_id, e["symbol"],
                                                   {"added_price": price}, watchlist_id=watchlist_id)
    return entries


def _reset_notifications(patch: dict) -> dict:
    """Changing a target/date re-arms its alert: drop the "already emailed" stamp so
    the new threshold can fire once. Clearing the field also clears the stamp."""
    if "alert_price" in patch:
        patch["alert_price_notified"] = None
    if "alert_date" in patch:
        patch["alert_date_notified"] = None
    return patch


def _fire_alert_check(owner_type: str, owner_id: str, alert_price, alert_date) -> None:
    """When a target price or alert date was just set, evaluate this watchlist right
    away (in the background) so a matching threshold emails immediately instead of
    waiting for the next 15-min sweep."""
    if alert_price is not None or alert_date:
        asyncio.create_task(check_owner(get_store(), owner_type, owner_id))


def _priced(entries: list[dict]) -> list[dict]:
    if not entries:
        return []
    symbols = [e["symbol"] for e in entries]
    quotes = get_quote_details(symbols)
    rows = []
    for e in entries:
        s = e["symbol"]
        q = quotes.get(s, {})
        meta = classify(s)
        price = q.get("price")
        added_price = e.get("added_price")
        diff = round(price - added_price, 2) if (price is not None and added_price is not None) else None
        diff_pct = round(diff / added_price * 100, 2) if (diff is not None and added_price) else None
        # A manual sector override wins over the classifier's guess; the classifier is
        # the fallback (typically for the "Unclassified" symbols it can't place).
        sector = e.get("sector") or meta["sector"]
        alert_price = e.get("alert_price")
        rows.append(
            {
                "symbol": s,
                "price": price,
                "change": q.get("change"),
                "change_pct": q.get("change_pct"),
                "sector": sector,
                "sector_custom": bool(e.get("sector")),
                "auto_sector": meta["sector"],
                "asset_class": meta["asset_class"],
                "added_date": e.get("added_date"),
                "added_price": added_price,
                "diff": diff,
                "diff_pct": diff_pct,
                "why": e.get("why") or "",
                "alert_date": e.get("alert_date"),
                "alert_price": alert_price,
                "alert_hit": (alert_price is not None and price is not None and price >= alert_price),
                "remarks": e.get("remarks") or "",
                "risks": e.get("risks") or "",
            }
        )
    return rows


# ── Manager watchlist ──────────────────────────────────────────────
@router.get("/managers/{manager_id}/watchlist")
async def get_manager_watchlist(manager_id: str):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    entries = await _backfill_added_prices(store, "MANAGER", manager_id, await store.get_watchlist("MANAGER", manager_id))
    return {"data": _priced(entries)}


@router.post("/managers/{manager_id}/watchlist")
async def add_manager_symbol(manager_id: str, body: WatchlistAdd):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    symbol = body.symbol.upper()
    added_price = _resolve_added_price(symbol, body.added_date)
    entries = await store.add_watchlist_symbol(
        "MANAGER", manager_id, symbol, added_price=added_price, why=body.why,
        alert_date=body.alert_date, added_date=body.added_date, remarks=body.remarks, risks=body.risks,
        sector=body.sector, alert_price=body.alert_price,
    )
    _fire_alert_check("MANAGER", manager_id, body.alert_price, body.alert_date)
    return {"data": _priced(entries)}


@router.patch("/managers/{manager_id}/watchlist/{symbol}")
async def update_manager_symbol(manager_id: str, symbol: str, body: WatchlistEntryUpdate):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    patch = _reset_notifications(body.model_dump(exclude_unset=True))
    entries = await store.update_watchlist_entry("MANAGER", manager_id, symbol.upper(), patch)
    _fire_alert_check("MANAGER", manager_id, patch.get("alert_price"), patch.get("alert_date"))
    return {"data": _priced(entries)}


@router.delete("/managers/{manager_id}/watchlist/{symbol}")
async def remove_manager_symbol(manager_id: str, symbol: str):
    store = get_store()
    entries = await store.remove_watchlist_symbol("MANAGER", manager_id, symbol)
    return {"data": _priced(entries)}


# ── Manager: multiple named watchlists ─────────────────────────────
# A manager can keep up to MAX_WATCHLISTS named lists. The endpoints above operate on
# the owner's default (first) list; these let the UI manage and address a specific one.
@router.get("/managers/{manager_id}/watchlists")
async def list_manager_watchlists(manager_id: str):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    return {"data": await store.list_watchlists("MANAGER", manager_id)}


@router.post("/managers/{manager_id}/watchlists")
async def create_manager_watchlist(manager_id: str, body: WatchlistMeta):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    name = body.name.strip() or "Untitled"
    existing = await store.list_watchlists("MANAGER", manager_id)
    if len(existing) >= MAX_WATCHLISTS:
        raise HTTPException(400, f"A manager can have at most {MAX_WATCHLISTS} watchlists")
    return {"data": await store.create_watchlist("MANAGER", manager_id, name)}


@router.patch("/managers/{manager_id}/watchlists/{watchlist_id}")
async def rename_manager_watchlist(manager_id: str, watchlist_id: str, body: WatchlistMeta):
    store = get_store()
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "name required")
    res = await store.rename_watchlist("MANAGER", manager_id, watchlist_id, name)
    if not res:
        raise HTTPException(404, "watchlist not found")
    return {"data": res}


@router.delete("/managers/{manager_id}/watchlists/{watchlist_id}")
async def delete_manager_watchlist(manager_id: str, watchlist_id: str):
    store = get_store()
    if len(await store.list_watchlists("MANAGER", manager_id)) <= 1:
        raise HTTPException(400, "Cannot delete the last watchlist")
    if not await store.delete_watchlist("MANAGER", manager_id, watchlist_id):
        raise HTTPException(404, "watchlist not found")
    return {"data": await store.list_watchlists("MANAGER", manager_id)}


@router.get("/managers/{manager_id}/watchlists/{watchlist_id}/entries")
async def get_manager_watchlist_entries(manager_id: str, watchlist_id: str):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    entries = await _backfill_added_prices(
        store, "MANAGER", manager_id,
        await store.get_watchlist("MANAGER", manager_id, watchlist_id), watchlist_id,
    )
    return {"data": _priced(entries)}


@router.post("/managers/{manager_id}/watchlists/{watchlist_id}/entries")
async def add_manager_watchlist_symbol(manager_id: str, watchlist_id: str, body: WatchlistAdd):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    symbol = body.symbol.upper()
    added_price = _resolve_added_price(symbol, body.added_date)
    entries = await store.add_watchlist_symbol(
        "MANAGER", manager_id, symbol, added_price=added_price, why=body.why,
        alert_date=body.alert_date, added_date=body.added_date, remarks=body.remarks, risks=body.risks,
        sector=body.sector, alert_price=body.alert_price, watchlist_id=watchlist_id,
    )
    _fire_alert_check("MANAGER", manager_id, body.alert_price, body.alert_date)
    return {"data": _priced(entries)}


@router.patch("/managers/{manager_id}/watchlists/{watchlist_id}/entries/{symbol}")
async def update_manager_watchlist_symbol(manager_id: str, watchlist_id: str, symbol: str, body: WatchlistEntryUpdate):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    patch = _reset_notifications(body.model_dump(exclude_unset=True))
    entries = await store.update_watchlist_entry("MANAGER", manager_id, symbol.upper(), patch, watchlist_id=watchlist_id)
    _fire_alert_check("MANAGER", manager_id, patch.get("alert_price"), patch.get("alert_date"))
    return {"data": _priced(entries)}


@router.delete("/managers/{manager_id}/watchlists/{watchlist_id}/entries/{symbol}")
async def remove_manager_watchlist_symbol(manager_id: str, watchlist_id: str, symbol: str):
    store = get_store()
    entries = await store.remove_watchlist_symbol("MANAGER", manager_id, symbol, watchlist_id=watchlist_id)
    return {"data": _priced(entries)}


# ── Client watchlist ───────────────────────────────────────────────
@router.get("/clients/{client_id}/watchlist")
async def get_client_watchlist(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    entries = await _backfill_added_prices(store, "CLIENT", client_id, await store.get_watchlist("CLIENT", client_id))
    return {"data": _priced(entries)}


@router.post("/clients/{client_id}/watchlist")
async def add_client_symbol(client_id: str, body: WatchlistAdd):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    symbol = body.symbol.upper()
    added_price = _resolve_added_price(symbol, body.added_date)
    entries = await store.add_watchlist_symbol(
        "CLIENT", client_id, symbol, added_price=added_price, why=body.why,
        alert_date=body.alert_date, added_date=body.added_date, remarks=body.remarks, risks=body.risks,
        sector=body.sector, alert_price=body.alert_price,
    )
    _fire_alert_check("CLIENT", client_id, body.alert_price, body.alert_date)
    return {"data": _priced(entries)}


@router.patch("/clients/{client_id}/watchlist/{symbol}")
async def update_client_symbol(client_id: str, symbol: str, body: WatchlistEntryUpdate):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    patch = _reset_notifications(body.model_dump(exclude_unset=True))
    entries = await store.update_watchlist_entry("CLIENT", client_id, symbol.upper(), patch)
    _fire_alert_check("CLIENT", client_id, patch.get("alert_price"), patch.get("alert_date"))
    return {"data": _priced(entries)}


@router.delete("/clients/{client_id}/watchlist/{symbol}")
async def remove_client_symbol(client_id: str, symbol: str):
    store = get_store()
    entries = await store.remove_watchlist_symbol("CLIENT", client_id, symbol)
    return {"data": _priced(entries)}


# ── Email alerts ────────────────────────────────────────────────────
class TestEmail(BaseModel):
    to: str


@router.get("/alerts/status")
async def alerts_status():
    """Whether email alerts can actually send, without leaking the password."""
    return {
        "enabled": settings.alerts_enabled,
        "configured": settings.alerts_ready,
        "from": settings.alert_email_from,
        "check_interval_seconds": settings.alert_check_interval_seconds,
    }


@router.post("/alerts/check")
async def alerts_check_now():
    """Run the target-price / alert-date sweep immediately (the background loop does
    this every alert_check_interval_seconds). Handy for testing."""
    return await check_and_send(get_store())


@router.post("/alerts/test")
async def alerts_test(body: TestEmail):
    """Send a one-off test email to confirm SMTP is wired up correctly."""
    try:
        send_email(body.to, "✅ Test alert — Portfolio Intelligence",
                   "This is a test email. Your watchlist alerts are configured correctly.")
    except MailNotConfigured:
        raise HTTPException(400, "Email not configured — set alert_smtp_password (a Gmail App Password).")
    except Exception as exc:
        raise HTTPException(502, f"SMTP send failed: {exc}")
    return {"sent": True, "to": body.to}
