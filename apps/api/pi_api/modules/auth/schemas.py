"""Pydantic schemas for the auth module."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    role: Literal["super_admin", "manager", "client"]
    manager_id: Optional[UUID] = None
    client_id: Optional[UUID] = None

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def new_password_min_length(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("new_password must be at least 8 characters")
        return v


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    refresh_token: str


class UserResponse(BaseModel):
    user_id: UUID
    email: str
    role: str
    manager_id: Optional[UUID]
    client_id: Optional[UUID]
    is_active: bool


class MeResponse(BaseModel):
    user_id: UUID
    email: str
    role: str
    manager_id: Optional[UUID]
    client_id: Optional[UUID]
