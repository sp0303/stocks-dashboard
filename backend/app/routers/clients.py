"""Manager routes: manage clients + tradebook upload (no auth in Phase 1)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile

import asyncio

from starlette.concurrency import run_in_threadpool

from app.models.schemas import ClientCreate, ClientUpdate
from app.routers.portfolio import _actions_for, cached_performance_series
from app.services import analytics, ingestion
from app.services.engine import compute_round_trips
from app.store import get_store

router = APIRouter(prefix="/api", tags=["clients"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/managers/{manager_id}/clients")
async def list_clients(manager_id: str):
    store = get_store()
    clients = await store.list_clients(manager_id)
    for c in clients:
        c["trade_count"] = await store.count_trades(c["id"])
    return {"data": clients}


@router.get("/managers/{manager_id}/metrics")
async def manager_metrics(manager_id: str):
    """Book-wide metrics aggregated across all of a manager's clients."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)
    payload = []
    for c in clients:
        payload.append({"id": c["id"], "name": c["name"], "trades": await store.list_trades(c["id"])})
    return {"data": analytics.manager_metrics(payload)}


@router.get("/managers/{manager_id}/performance")
async def manager_performance(manager_id: str):
    """Manager-level performance, in two parts:
    - "book": the whole book's value summed across every client's own real,
      mark-to-market performance curve, compared against the same 4 benchmark indices
      used on a client's own Performance tab — the manager's overall portfolio vs.
      Nifty/Midcap/Largecap/Smallcap.
    - "clients": each client's own % return over time (NOT absolute ₹ — clients deploy
      wildly different capital, so only a normalized return is fair to plot on one shared
      chart; a client with 10x the capital would otherwise dominate the y-axis with no
      bearing on who's actually performing better).
    Every client's real prices are fetched concurrently so this scales reasonably with
    book size."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)

    async def _one_client(c: dict) -> tuple[list[dict] | None, dict | None]:
        trades = await store.list_trades(c["id"])
        if not trades:
            return None, None
        actions = await _actions_for(trades)
        series = await cached_performance_series(c["id"], trades, actions)
        pct_series = [
            {
                "date": row["date"],
                "return_pct": round((row["total_value"] - row["invested_value"]) / row["invested_value"] * 100, 2)
                if row.get("total_value") is not None and row.get("invested_value") else 0.0,
            }
            for row in series
        ]
        return series, {"id": c["id"], "name": c["name"], "series": pct_series}

    results = await asyncio.gather(*(_one_client(c) for c in clients))
    client_series = [r[0] for r in results if r[0]]
    client_summaries = [r[1] for r in results if r[1] is not None]

    book = analytics.aggregate_performance_series(client_series)
    return {"data": {"book": book, "clients": client_summaries}}


@router.get("/managers/{manager_id}/holdings")
async def manager_holdings(manager_id: str, client_ids: str = None):
    """Aggregated holdings across selected clients for a manager.
    Returns holdings grouped by symbol with client names, quantities, and holding %.

    Args:
        manager_id: The manager's ID
        client_ids: Comma-separated list of client IDs to include (all if not specified)
    """
    from app.services import analytics

    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")

    all_clients = await store.list_clients(manager_id)
    if not all_clients:
        return {"data": {"holdings": [], "totals": {"market_value": 0, "invested_value": 0, "unrealized_pnl": 0}}}

    # Filter clients if specific ones requested
    if client_ids:
        requested = set(client_ids.split(","))
        clients = [c for c in all_clients if c["id"] in requested]
    else:
        clients = all_clients

    if not clients:
        raise HTTPException(400, "no valid clients selected")

    # Aggregate holdings from all selected clients
    aggregated = {}
    totals = {"market_value": 0, "invested_value": 0, "unrealized_pnl": 0}

    for client in clients:
        trades = await store.list_trades(client["id"])
        if not trades:
            continue

        actions = await _actions_for(trades)
        holdings_data = analytics.build_holdings(trades, with_prices=True, actions=actions)

        for holding in holdings_data.get("holdings", []):
            symbol = holding["symbol"]
            qty = holding.get("quantity") or 0  # Use "quantity" not "qty"; coerce None→0

            if symbol not in aggregated:
                aggregated[symbol] = {
                    "symbol": symbol,
                    "qty": 0,
                    "buy_avg": 0,
                    "buy_value": 0,
                    "ltp": holding.get("ltp", 0),
                    "present_value": 0,
                    "pnl": 0,
                    "pnl_pct": 0,
                    "clients": []
                }

            # Add this client's contribution (coerce None→0: a symbol Angel couldn't price
            # returns market_value/pnl = None, which used to crash the += aggregation).
            aggregated[symbol]["qty"] += qty
            aggregated[symbol]["buy_value"] += holding.get("invested_value") or 0
            aggregated[symbol]["present_value"] += holding.get("market_value") or 0
            aggregated[symbol]["pnl"] += holding.get("unrealized_pnl") or 0
            aggregated[symbol]["ltp"] = holding.get("ltp") or aggregated[symbol]["ltp"]

            # Track which client holds this with full name
            if qty > 0:
                aggregated[symbol]["clients"].append({
                    "name": client["name"],
                    "qty": qty
                })

        # Update totals (coerce None→0)
        _t = holdings_data.get("totals", {})
        totals["market_value"] += _t.get("market_value") or 0
        totals["invested_value"] += _t.get("invested_value") or 0
        totals["unrealized_pnl"] += _t.get("unrealized_pnl") or 0

    # Calculate buy average and percentages
    holdings_list = []
    for symbol, data in aggregated.items():
        # Calculate buy average from invested value and quantity
        if data["qty"] > 0:
            data["buy_avg"] = data["buy_value"] / data["qty"]
        else:
            data["buy_avg"] = 0

        # Calculate P&L percentage
        if data["buy_value"] > 0:
            data["pnl_pct"] = (data["pnl"] / data["buy_value"] * 100)
        else:
            data["pnl_pct"] = 0

        # Calculate holding percentage
        holding_pct = (data["present_value"] / totals["market_value"] * 100) if totals["market_value"] > 0 else 0
        data["holding_pct"] = holding_pct

        holdings_list.append(data)

    # Sort by market value descending
    holdings_list.sort(key=lambda x: x["present_value"], reverse=True)

    return {
        "data": {
            "holdings": holdings_list,
            "totals": totals,
            "client_count": len(clients)
        }
    }


@router.get("/managers/{manager_id}/trade-log")
async def manager_trade_log(manager_id: str):
    """Flat closed-trade log across every client — one row per FIFO round trip, with the
    client as the 'account' and the buy-trade note as 'reason for buying'. This is the
    spreadsheet-style journal view: Account | Stock | Qty | Buy | Sell | Days | PNL |
    PNL% | Reason. Round trips are computed in-process (no external calls)."""
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)

    rows: list[dict] = []
    for c in clients:
        trades = await store.list_trades(c["id"])
        if not trades:
            continue
        rts = await run_in_threadpool(compute_round_trips, trades)
        journal = await store.get_trade_journal(c["id"])
        for rt in rts:
            note = (journal.get(rt.get("buy_fingerprint")) or {}).get("note", "")
            rows.append({
                "account": c["name"],
                "client_id": c["id"],
                "symbol": rt["symbol"],
                "quantity": rt["quantity"],
                "buy_price": rt["buy_price"],
                "sell_price": rt["sell_price"],
                "buy_date": rt.get("buy_date"),
                "sell_date": rt.get("sell_date"),
                "days": rt["days"],
                "pnl": rt["pnl"],
                "pnl_pct": rt["pnl_pct"],
                "reason": note,
                "buy_fingerprint": rt.get("buy_fingerprint"),
            })
    rows.sort(key=lambda r: r.get("sell_date") or "", reverse=True)
    return {"data": rows, "meta": {"total": len(rows), "clients": len(clients)}}


@router.get("/clients")
async def list_all_clients():
    store = get_store()
    clients = await store.list_clients()
    for c in clients:
        c["trade_count"] = await store.count_trades(c["id"])
    return {"data": clients}


@router.post("/clients")
async def create_client(body: ClientCreate):
    store = get_store()
    if not await store.get_manager(body.portfolio_manager_id):
        raise HTTPException(404, "portfolio manager not found")
    doc = {
        **body.model_dump(),
        "status": "ACTIVE",
        "onboarded_at": _now(),
        "created_at": _now(),
    }
    return {"data": await store.create_client(doc)}


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    store = get_store()
    c = await store.get_client(client_id)
    if not c:
        raise HTTPException(404, "client not found")
    c["trade_count"] = await store.count_trades(client_id)
    return {"data": c}


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, body: ClientUpdate):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await store.update_client(client_id, patch)
    if not updated:
        raise HTTPException(404, "client not found")
    return {"data": updated}


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str):
    store = get_store()
    if not await store.get_client(client_id):
        raise HTTPException(404, "client not found")
    # cascades trades + uploads + watchlist in the store
    await store.delete_client(client_id)
    return {"data": {"deleted": client_id}}


@router.post("/clients/{client_id}/tradebooks")
async def upload_tradebook(client_id: str, file: UploadFile = File(...)):
    store = get_store()
    client = await store.get_client(client_id)
    if not client:
        raise HTTPException(404, "client not found")

    content = await file.read()
    fhash = ingestion.file_hash(content)
    if await store.upload_exists(client_id, fhash):
        raise HTTPException(409, "this exact file was already uploaded")

    import io

    parsed = ingestion.parse_tradebook(io.BytesIO(content), client_id_hint=client.get("client_code"))
    if not parsed.trades:
        raise HTTPException(422, f"no valid trades found ({'; '.join(parsed.errors[:3])})")

    # tag every trade with our internal client id
    for t in parsed.trades:
        t["client_id"] = client_id

    version = await store.next_upload_version(client_id)
    inserted, dupes = await store.insert_trades(parsed.trades)

    upload = await store.create_upload(
        {
            "client_id": client_id,
            "version": version,
            "file_name": file.filename,
            "file_hash": fhash,
            "uploaded_at": _now(),
            "date_from": parsed.date_from,
            "date_to": parsed.date_to,
            "row_count": len(parsed.trades),
            "imported_count": inserted,
            "duplicate_count": dupes,
            "error_count": len(parsed.errors),
            "status": "IMPORTED" if not parsed.errors else "PARTIAL",
        }
    )
    # if the excel carried a client code and the client didn't have one, store it
    if parsed.client_id and not client.get("client_code"):
        await store.update_client(client_id, {"client_code": parsed.client_id})

    return {
        "data": {
            "upload": upload,
            "summary": {
                "parsed": len(parsed.trades),
                "imported": inserted,
                "duplicates": dupes,
                "errors": len(parsed.errors),
            },
        }
    }


@router.get("/clients/{client_id}/tradebooks")
async def list_uploads(client_id: str):
    store = get_store()
    return {"data": await store.list_uploads(client_id)}
