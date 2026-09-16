"""Super-admin routes: manage portfolio managers (no auth in Phase 1)."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.models.schemas import ManagerCreate, ManagerUpdate
from app.services import auth
from app.store import get_store

# Every Super Admin route requires the admin session.
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(auth.require_admin)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/managers")
async def list_managers():
    store = get_store()
    managers = await store.list_managers()
    for m in managers:
        clients = await store.list_clients(m["id"])
        m["client_count"] = len(clients)
        m.pop("password_hash", None)          # never expose the hash to the client
    return {"data": managers}


@router.post("/managers")
async def create_manager(body: ManagerCreate):
    store = get_store()
    if not (body.email or "").strip():
        raise HTTPException(400, "email is required — managers log in with email + password")
    email = body.email.strip().lower()
    if any((m.get("email") or "").strip().lower() == email for m in await store.list_managers()):
        raise HTTPException(409, "a manager with this email already exists")
    doc = {
        **body.model_dump(),
        "email": body.email.strip(),
        "status": "ACTIVE",
        "created_at": _now(),
        # Default password (settings.default_manager_password); the manager changes it later.
        "password_hash": auth.hash_password(settings.default_manager_password),
    }
    return {"data": await store.create_manager(doc)}


@router.patch("/managers/{manager_id}")
async def update_manager(manager_id: str, body: ManagerUpdate):
    store = get_store()
    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await store.update_manager(manager_id, patch)
    if not updated:
        raise HTTPException(404, "manager not found")
    return {"data": updated}


@router.delete("/managers/{manager_id}")
async def delete_manager(manager_id: str):
    store = get_store()
    if not await store.get_manager(manager_id):
        raise HTTPException(404, "manager not found")
    clients = await store.list_clients(manager_id)
    if clients:
        raise HTTPException(
            409, f"manager still has {len(clients)} client(s); reassign or delete them first"
        )
    await store.delete_manager(manager_id)
    return {"data": {"deleted": manager_id}}


@router.get("/overview")
async def platform_overview():
    """Super-admin landing summary — one glance tells you the platform state."""
    store = get_store()
    managers = await store.list_managers()
    clients = await store.list_clients()
    total_trades = 0
    for c in clients:
        total_trades += await store.count_trades(c["id"])
    return {
        "data": {
            "managers": len(managers),
            "clients": len(clients),
            "total_trades": total_trades,
            "active_managers": sum(1 for m in managers if m.get("status") == "ACTIVE"),
        }
    }
