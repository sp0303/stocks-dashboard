"""Basic password auth + session tokens (Phase 1; Google auth planned later).

Two roles:
  * admin   — the Super Admin. One password (settings.admin_password / ADMIN_PASSWORD).
  * manager — logs in with email + password; scoped to their own clients only.

Passwords are stored as salted PBKDF2 hashes (stdlib — no external dependency). Sessions are
stateless HMAC-signed tokens (also stdlib): `<base64url(payload)>.<hex hmac>`, carrying the
role, the manager_id (for managers) and an expiry. Not JWT, but the same shape and enough for
a password gate; swap for real OAuth later without touching call sites.

FastAPI dependencies enforce access:
  * require_admin           — admin only (Super Admin routes).
  * require_manager_scope   — admin, or the manager whose id is in the path.
  * require_client_access   — admin, or the manager who owns that client.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException

from app.config import settings

_ITER = 200_000
_ALGO = "pbkdf2_sha256"


# ── password hashing ──────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"{_ALGO}${_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != _ALGO:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


# ── stateless session tokens ──────────────────────────────────────
def _secret() -> bytes:
    return settings.auth_secret.encode()


def make_token(payload: dict, ttl_hours: int = 24 * 14) -> str:
    body = {**payload, "exp": int(time.time()) + ttl_hours * 3600}
    raw = base64.urlsafe_b64encode(json.dumps(body).encode()).decode().rstrip("=")
    sig = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def verify_token(token: str) -> dict | None:
    try:
        raw, sig = token.split(".")
    except ValueError:
        return None
    expected = hmac.new(_secret(), raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    except (ValueError, json.JSONDecodeError):
        return None
    if float(body.get("exp", 0)) < time.time():
        return None
    return body


# ── identity + FastAPI dependencies ───────────────────────────────
@dataclass
class Identity:
    role: str                       # 'admin' | 'manager'
    manager_id: str | None = None


def get_identity(authorization: str = Header(default="")) -> Identity:
    token = authorization[7:].strip() if authorization[:7].lower() == "bearer " else ""
    body = verify_token(token) if token else None
    if not body or body.get("role") not in ("admin", "manager"):
        raise HTTPException(401, "not authenticated")
    return Identity(role=body["role"], manager_id=body.get("manager_id"))


def require_admin(ident: Identity = Depends(get_identity)) -> Identity:
    if ident.role != "admin":
        raise HTTPException(403, "admin only")
    return ident


def require_manager_scope(manager_id: str, ident: Identity = Depends(get_identity)) -> Identity:
    """Path has {manager_id}: admin sees any, a manager sees only their own."""
    if ident.role == "admin" or ident.manager_id == manager_id:
        return ident
    raise HTTPException(403, "you can only access your own book")


async def require_client_access(client_id: str, ident: Identity = Depends(get_identity)) -> Identity:
    """Path has {client_id}: admin sees any, a manager only clients they own."""
    if ident.role == "admin":
        return ident
    from app.store import get_store
    client = await get_store().get_client(client_id)
    if not client or client.get("portfolio_manager_id") != ident.manager_id:
        raise HTTPException(403, "you can only access your own clients")
    return ident
