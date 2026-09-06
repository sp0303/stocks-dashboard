"""Manager routes: manage clients + tradebook upload (no auth in Phase 1)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, File, HTTPException, UploadFile

import asyncio

from app.models.schemas import ClientCreate, ClientUpdate
from app.routers.portfolio import _actions_for, compute_performance_series
from app.services import analytics, ingestion
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
        series = await compute_performance_series(trades, actions)
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
