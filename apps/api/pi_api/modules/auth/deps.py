"""FastAPI auth dependencies — get_current_user, require_manager, etc."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from pi_api.modules.auth.service import decode_access_token

_bearer = HTTPBearer(auto_error=True)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)

_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions",
)


@dataclass(frozen=True)
class Principal:
    """Decoded JWT claims attached to each request."""

    user_id: uuid.UUID
    role: str
    manager_id: Optional[uuid.UUID]
    client_id: Optional[uuid.UUID]


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> Principal:
    """Validate Bearer JWT and return the decoded Principal."""
    try:
        payload = decode_access_token(creds.credentials)
    except JWTError:
        raise _UNAUTHORIZED

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise _UNAUTHORIZED

    manager_id_str = payload.get("manager_id")
    client_id_str = payload.get("client_id")

    return Principal(
        user_id=uuid.UUID(sub),
        role=role,
        manager_id=uuid.UUID(manager_id_str) if manager_id_str else None,
        client_id=uuid.UUID(client_id_str) if client_id_str else None,
    )


async def require_manager(principal: Principal = Depends(get_current_user)) -> Principal:
    """Allow super_admin and manager roles only."""
    if principal.role not in ("super_admin", "manager"):
        raise _FORBIDDEN
    return principal


async def require_super_admin(principal: Principal = Depends(get_current_user)) -> Principal:
    """Allow super_admin only."""
    if principal.role != "super_admin":
        raise _FORBIDDEN
    return principal
