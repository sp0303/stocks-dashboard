"""Login + session for the basic password gate.

  POST /api/auth/login            {role:'admin', password}                  -> {token, role}
  POST /api/auth/login            {role:'manager', email, password}         -> {token, role, manager}
  GET  /api/auth/me               (Bearer token)                            -> current identity
  POST /api/auth/change-password  {old_password, new_password} (manager)    -> ok
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.services import auth
from app.store import get_store

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginBody(BaseModel):
    role: str                       # 'admin' | 'manager'
    email: str | None = None
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str


def _manager_public(m: dict) -> dict:
    return {"id": m["id"], "name": m.get("name"), "firm": m.get("firm"), "email": m.get("email")}


@router.post("/login")
async def login(body: LoginBody):
    if body.role == "admin":
        if not hmac.compare_digest(body.password, settings.admin_password):
            raise HTTPException(401, "wrong password")
        return {"data": {"token": auth.make_token({"role": "admin"}), "role": "admin"}}

    if body.role == "manager":
        if not body.email:
            raise HTTPException(400, "email required")
        managers = await get_store().list_managers()
        email = body.email.strip().lower()
        m = next((x for x in managers if (x.get("email") or "").strip().lower() == email), None)
        if not m or not m.get("password_hash") or not auth.verify_password(body.password, m["password_hash"]):
            raise HTTPException(401, "wrong email or password")
        if m.get("status") and m["status"] != "ACTIVE":
            raise HTTPException(403, "account disabled")
        token = auth.make_token({"role": "manager", "manager_id": m["id"]})
        return {"data": {"token": token, "role": "manager", "manager": _manager_public(m)}}

    raise HTTPException(400, "unknown role")


@router.get("/me")
async def me(ident: auth.Identity = Depends(auth.get_identity)):
    if ident.role == "admin":
        return {"data": {"role": "admin"}}
    m = await get_store().get_manager(ident.manager_id)
    if not m:
        raise HTTPException(401, "session invalid")
    return {"data": {"role": "manager", "manager": _manager_public(m)}}


@router.post("/change-password")
async def change_password(body: ChangePasswordBody,
                          ident: auth.Identity = Depends(auth.get_identity)):
    if ident.role != "manager":
        raise HTTPException(400, "the admin password is set via ADMIN_PASSWORD in the server env")
    if len(body.new_password) < 6:
        raise HTTPException(400, "new password must be at least 6 characters")
    store = get_store()
    m = await store.get_manager(ident.manager_id)
    if not m or not m.get("password_hash") or not auth.verify_password(body.old_password, m["password_hash"]):
        raise HTTPException(403, "current password is wrong")
    await store.update_manager(ident.manager_id, {"password_hash": auth.hash_password(body.new_password)})
    return {"data": {"ok": True}}
