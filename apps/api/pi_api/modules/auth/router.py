"""Auth router — /api/v1/auth endpoints."""

from __future__ import annotations

import uuid
from datetime import timezone
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Response, status

from pi_api.core.db import get_db_connection
from pi_api.modules.auth import repository as repo
from pi_api.modules.auth.deps import Principal, get_current_user, require_super_admin
from pi_api.modules.auth.schemas import (
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    MeResponse,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)
from pi_api.modules.auth.service import (
    create_access_token,
    create_refresh_token,
    hash_password,
    needs_rehash,
    verify_password,
)
from pi_api.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])

_401 = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bad credentials")
_409 = HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")


# --------------------------------------------------------------------------- #
# POST /auth/login
# --------------------------------------------------------------------------- #


@router.post("/login", response_model=TokenResponse, summary="Login with email + password")
async def login(
    body: LoginRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
) -> TokenResponse:
    user = await repo.get_user_by_email(conn, body.email)
    if not user or not user["is_active"]:
        raise _401
    if not verify_password(body.password, user["password_hash"]):
        raise _401

    user_id = user["user_id"]

    # Opportunistically rehash if parameters changed
    if needs_rehash(user["password_hash"]):
        new_hash = hash_password(body.password)
        await repo.update_password_hash(conn, user_id, new_hash)

    await repo.update_last_login(conn, user_id)

    access_token, expires_at = create_access_token(
        user_id=user_id,
        role=user["role"],
        manager_id=user["manager_id"],
        client_id=user["client_id"],
    )
    raw_refresh, refresh_expires = create_refresh_token()
    await repo.store_refresh_token(conn, user_id, raw_refresh, refresh_expires)

    await repo.write_audit_log(
        conn,
        user_id=user_id,
        action="login",
        meta={"email": body.email},
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh,
    )


# --------------------------------------------------------------------------- #
# POST /auth/refresh
# --------------------------------------------------------------------------- #


@router.post("/refresh", response_model=TokenResponse, summary="Refresh access token")
async def refresh(
    body: RefreshRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
) -> TokenResponse:
    from datetime import datetime

    record = await repo.get_refresh_token(conn, body.refresh_token)
    if not record or record["revoked"]:
        raise _401

    # Check expiry
    expires_at = record["expires_at"]
    now = datetime.now(timezone.utc)
    if expires_at.tzinfo is None:
        from datetime import timezone as tz

        expires_at = expires_at.replace(tzinfo=tz.utc)
    if now > expires_at:
        raise _401

    user = await repo.get_user_by_id(conn, record["user_id"])
    if not user or not user["is_active"]:
        raise _401

    # Rotate refresh token (revoke old, issue new)
    await repo.revoke_refresh_token(conn, body.refresh_token)
    raw_refresh, new_refresh_expires = create_refresh_token()
    await repo.store_refresh_token(conn, user["user_id"], raw_refresh, new_refresh_expires)

    access_token, _ = create_access_token(
        user_id=user["user_id"],
        role=user["role"],
        manager_id=user["manager_id"],
        client_id=user["client_id"],
    )

    return TokenResponse(
        access_token=access_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        refresh_token=raw_refresh,
    )


# --------------------------------------------------------------------------- #
# POST /auth/logout
# --------------------------------------------------------------------------- #


@router.post("/logout", status_code=204, summary="Logout (revoke refresh token)", response_class=Response)
async def logout(
    body: RefreshRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
    _: Principal = Depends(get_current_user),
) -> Response:
    await repo.revoke_refresh_token(conn, body.refresh_token)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# GET /auth/me
# --------------------------------------------------------------------------- #


@router.get("/me", response_model=MeResponse, summary="Current user info")
async def me(principal: Principal = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        email="",  # not stored in token; fetch from DB if needed
        role=principal.role,
        manager_id=principal.manager_id,
        client_id=principal.client_id,
    )


@router.get("/me/full", response_model=UserResponse, summary="Current user info (from DB)")
async def me_full(
    principal: Principal = Depends(get_current_user),
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)] = None,
) -> UserResponse:
    user = await repo.get_user_by_id(conn, principal.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**dict(user))


# --------------------------------------------------------------------------- #
# POST /auth/users  (super_admin only)
# --------------------------------------------------------------------------- #


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=201,
    summary="Create a new user (super_admin only)",
)
async def create_user(
    body: CreateUserRequest,
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)],
    _: Principal = Depends(require_super_admin),
) -> UserResponse:
    existing = await repo.get_user_by_email(conn, body.email)
    if existing:
        raise _409

    password_hash = hash_password(body.password)
    user = await repo.create_user(
        conn,
        email=body.email,
        password_hash=password_hash,
        role=body.role,
        manager_id=body.manager_id,
        client_id=body.client_id,
    )
    return UserResponse(**dict(user))


# --------------------------------------------------------------------------- #
# POST /auth/change-password
# --------------------------------------------------------------------------- #


@router.post("/change-password", status_code=204, summary="Change own password", response_class=Response)
async def change_password(
    body: ChangePasswordRequest,
    principal: Principal = Depends(get_current_user),
    conn: Annotated[asyncpg.Connection, Depends(get_db_connection)] = None,
) -> Response:
    user = await repo.get_user_by_id(conn, principal.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(body.new_password)
    await repo.update_password_hash(conn, principal.user_id, new_hash)
    # Revoke all refresh tokens (force re-login everywhere)
    await repo.revoke_all_refresh_tokens(conn, principal.user_id)
    await repo.write_audit_log(
        conn,
        user_id=principal.user_id,
        action="change_password",
    )
    return Response(status_code=204)
