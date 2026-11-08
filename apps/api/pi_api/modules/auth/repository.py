"""Auth repository — all SQL against auth.* and core.* tables."""

from __future__ import annotations

import hashlib
import os
import uuid
from typing import Any, Optional

import asyncpg


# --------------------------------------------------------------------------- #
# User queries
# --------------------------------------------------------------------------- #


async def get_user_by_email(conn: asyncpg.Connection, email: str) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        """
        SELECT user_id, email, password_hash, role,
               manager_id, client_id, is_active
        FROM auth.users
        WHERE email = $1
        """,
        email,
    )


async def get_user_by_id(conn: asyncpg.Connection, user_id: uuid.UUID) -> Optional[asyncpg.Record]:
    return await conn.fetchrow(
        """
        SELECT user_id, email, password_hash, role,
               manager_id, client_id, is_active
        FROM auth.users
        WHERE user_id = $1
        """,
        user_id,
    )


async def create_user(
    conn: asyncpg.Connection,
    email: str,
    password_hash: str,
    role: str,
    manager_id: Optional[uuid.UUID],
    client_id: Optional[uuid.UUID],
) -> asyncpg.Record:
    return await conn.fetchrow(
        """
        INSERT INTO auth.users (email, password_hash, role, manager_id, client_id)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING user_id, email, role, manager_id, client_id, is_active
        """,
        email,
        password_hash,
        role,
        manager_id,
        client_id,
    )


async def update_last_login(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await conn.execute(
        "UPDATE auth.users SET last_login_at = now() WHERE user_id = $1",
        user_id,
    )


async def update_password_hash(
    conn: asyncpg.Connection, user_id: uuid.UUID, new_hash: str
) -> None:
    await conn.execute(
        "UPDATE auth.users SET password_hash = $1 WHERE user_id = $2",
        new_hash,
        user_id,
    )


# --------------------------------------------------------------------------- #
# Refresh-token queries
# --------------------------------------------------------------------------- #


def _hash_token(raw: str) -> bytes:
    """SHA-256 hash of the raw token string — stored in auth.refresh_tokens."""
    return hashlib.sha256(raw.encode()).digest()


async def store_refresh_token(
    conn: asyncpg.Connection,
    user_id: uuid.UUID,
    raw_token: str,
    expires_at: Any,  # datetime
) -> None:
    token_hash = _hash_token(raw_token)
    await conn.execute(
        """
        INSERT INTO auth.refresh_tokens (token_hash, user_id, expires_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (token_hash) DO NOTHING
        """,
        token_hash,
        user_id,
        expires_at,
    )


async def get_refresh_token(
    conn: asyncpg.Connection, raw_token: str
) -> Optional[asyncpg.Record]:
    token_hash = _hash_token(raw_token)
    return await conn.fetchrow(
        """
        SELECT token_hash, user_id, expires_at, revoked
        FROM auth.refresh_tokens
        WHERE token_hash = $1
        """,
        token_hash,
    )


async def revoke_refresh_token(conn: asyncpg.Connection, raw_token: str) -> None:
    token_hash = _hash_token(raw_token)
    await conn.execute(
        "UPDATE auth.refresh_tokens SET revoked = true WHERE token_hash = $1",
        token_hash,
    )


async def revoke_all_refresh_tokens(conn: asyncpg.Connection, user_id: uuid.UUID) -> None:
    await conn.execute(
        "UPDATE auth.refresh_tokens SET revoked = true WHERE user_id = $1",
        user_id,
    )


async def purge_expired_refresh_tokens(conn: asyncpg.Connection) -> int:
    result = await conn.execute(
        "DELETE FROM auth.refresh_tokens WHERE expires_at < now() OR revoked = true"
    )
    # result is like "DELETE N"
    return int(result.split()[-1]) if result else 0


# --------------------------------------------------------------------------- #
# Audit log
# --------------------------------------------------------------------------- #


async def write_audit_log(
    conn: asyncpg.Connection,
    *,
    user_id: Optional[uuid.UUID],
    action: str,
    entity: Optional[str] = None,
    entity_id: Optional[str] = None,
    meta: Optional[dict] = None,
) -> None:
    import json

    await conn.execute(
        """
        INSERT INTO auth.audit_log (user_id, action, entity, entity_id, meta)
        VALUES ($1, $2, $3, $4, $5)
        """,
        user_id,
        action,
        entity,
        entity_id,
        json.dumps(meta) if meta else None,
    )
