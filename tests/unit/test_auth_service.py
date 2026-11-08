"""Unit tests for auth service (password hashing and JWT)."""

from __future__ import annotations

import time
import uuid
from datetime import timedelta

import pytest

from pi_api.modules.auth.service import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    needs_rehash,
    verify_password,
)


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #


def test_hash_and_verify_password() -> None:
    pw = "s3cr3tPassword!"
    h = hash_password(pw)
    assert h != pw
    assert h.startswith("$argon2id$")
    assert verify_password(pw, h) is True


def test_wrong_password_fails_verify() -> None:
    h = hash_password("correct")
    assert verify_password("wrong", h) is False


def test_needs_rehash_on_fresh_hash_is_false() -> None:
    h = hash_password("password123")
    assert needs_rehash(h) is False


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #


def test_access_token_roundtrip() -> None:
    uid = uuid.uuid4()
    manager_id = uuid.uuid4()
    token, expires_at = create_access_token(
        user_id=uid,
        role="manager",
        manager_id=manager_id,
        expires_delta=timedelta(minutes=5),
    )
    payload = decode_access_token(token)
    assert payload["sub"] == str(uid)
    assert payload["role"] == "manager"
    assert payload["manager_id"] == str(manager_id)
    assert payload["client_id"] is None


def test_expired_token_raises() -> None:
    from jose import JWTError

    uid = uuid.uuid4()
    token, _ = create_access_token(
        user_id=uid,
        role="super_admin",
        expires_delta=timedelta(seconds=-1),  # already expired
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_tampered_token_raises() -> None:
    from jose import JWTError

    uid = uuid.uuid4()
    token, _ = create_access_token(user_id=uid, role="manager")
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_access_token(tampered)


def test_refresh_token_is_opaque_and_long() -> None:
    raw, expires_at = create_refresh_token()
    # Should be a URL-safe base64 string, at least 64 chars
    assert isinstance(raw, str)
    assert len(raw) >= 64
    # Two tokens should not be equal
    raw2, _ = create_refresh_token()
    assert raw != raw2


def test_access_token_has_jti() -> None:
    """Each token should have a unique jti claim."""
    uid = uuid.uuid4()
    t1, _ = create_access_token(user_id=uid, role="super_admin")
    t2, _ = create_access_token(user_id=uid, role="super_admin")
    p1 = decode_access_token(t1)
    p2 = decode_access_token(t2)
    assert p1["jti"] != p2["jti"]
