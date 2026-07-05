"""Pydantic request/response schemas for the auth API."""

from __future__ import annotations

import datetime as dt
import uuid

from pydantic import BaseModel, ConfigDict, EmailStr


# --- roles -------------------------------------------------------------------
class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    permissions: list[str]
    is_system: bool
    created_at: dt.datetime


class CreateRoleIn(BaseModel):
    name: str
    description: str | None = None
    permissions: list[str] = []


class UpdateRoleIn(BaseModel):
    name: str | None = None
    description: str | None = None
    permissions: list[str] | None = None


# --- users -------------------------------------------------------------------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    full_name: str | None
    role: RoleOut
    is_active: bool
    email_verified: bool
    created_at: dt.datetime
    last_login_at: dt.datetime | None
    # Resolved from the stored avatar_key at response time (None => use initials).
    avatar_url: str | None = None
    preferences: dict = {}
    # Whether the user has an active TOTP second factor.
    totp_enabled: bool = False


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginResult(BaseModel):
    """Login response. Either issues tokens directly, or (when the user has 2FA)
    returns ``mfa_required`` + a short-lived ``mfa_token`` to exchange via
    ``/auth/login/mfa``."""

    mfa_required: bool = False
    mfa_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"


class MfaLoginIn(BaseModel):
    mfa_token: str
    code: str


class TotpConfirmIn(BaseModel):
    code: str


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_uri: str


class RecoveryCodesOut(BaseModel):
    recovery_codes: list[str]


class TotpStatusOut(BaseModel):
    enabled: bool
    recovery_codes_remaining: int


class RefreshIn(BaseModel):
    refresh_token: str


class LogoutIn(BaseModel):
    refresh_token: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    token: str
    new_password: str


class AccessOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SetupIn(BaseModel):
    """First-run setup: create the very first administrator (only when none exist)."""

    email: EmailStr
    password: str
    full_name: str | None = None


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    role_id: uuid.UUID
    is_active: bool = True
    # When true, email the new user a welcome + "set your password" invite link.
    send_invite: bool = False


class UpdateUserIn(BaseModel):
    role_id: uuid.UUID | None = None
    is_active: bool | None = None
    full_name: str | None = None


class ConfirmPasswordIn(BaseModel):
    """The acting admin re-enters their own password to confirm a sensitive action."""

    password: str


class UpdateMeIn(BaseModel):
    """Self-service profile edit (the signed-in user updates their own record)."""

    full_name: str | None = None


class PreferencesIn(BaseModel):
    """Partial merge into the user's preferences JSON (only sent keys change)."""

    preferences: dict


class SessionOut(BaseModel):
    """A live login session (backed by a non-revoked refresh token)."""

    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    user_agent: str | None
    ip: str | None
    created_at: dt.datetime
    last_used_at: dt.datetime | None
    current: bool = False


# --- API keys ----------------------------------------------------------------
class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    prefix: str
    role: RoleOut
    is_active: bool
    created_at: dt.datetime
    last_used_at: dt.datetime | None


class ApiKeyCreateIn(BaseModel):
    name: str
    role_id: uuid.UUID


class ApiKeyCreatedOut(ApiKeyOut):
    key: str  # the raw key — returned ONCE at creation, never again
