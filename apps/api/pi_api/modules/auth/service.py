"""Auth service — password hashing (argon2id) and JWT creation/verification."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import JWTError, jwt

from pi_api.settings import settings

# argon2id hasher — OWASP recommended parameters
_ph = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)

_REFRESH_TOKEN_BYTES = 64  # 512-bit opaque random token


# --------------------------------------------------------------------------- #
# Password helpers
# --------------------------------------------------------------------------- #


def hash_password(plain: str) -> str:
    """Hash plain-text password with argon2id."""
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed. Never raises on mismatch."""
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed: str) -> bool:
    """True when the hash was created with outdated parameters."""
    return _ph.check_needs_rehash(hashed)


# --------------------------------------------------------------------------- #
# JWT helpers
# --------------------------------------------------------------------------- #


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: uuid.UUID,
    role: str,
    manager_id: Optional[uuid.UUID] = None,
    client_id: Optional[uuid.UUID] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, datetime]:
    """Return (encoded_jwt, expires_at)."""
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    expires_at = _utcnow() + expires_delta
    payload = {
        "sub": str(user_id),
        "role": role,
        "manager_id": str(manager_id) if manager_id else None,
        "client_id": str(client_id) if client_id else None,
        "exp": expires_at,
        "iat": _utcnow(),
        "jti": secrets.token_hex(16),
    }
    encoded = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded, expires_at


def create_refresh_token() -> tuple[str, datetime]:
    """Return (opaque_token, expires_at). Stored hashed in DB."""
    raw = secrets.token_urlsafe(_REFRESH_TOKEN_BYTES)
    expires_at = _utcnow() + timedelta(days=30)
    return raw, expires_at


def decode_access_token(token: str) -> dict:
    """Decode and verify JWT. Raises JWTError on any failure."""
    return jwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
    )
