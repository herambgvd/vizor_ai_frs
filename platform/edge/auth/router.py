"""Auth API: session + permission catalog + dynamic roles + users + API keys.

Mounted always-on via ``create_app(registry, extra_routers=[auth.router])``.
Access is permission-gated (require_permission), never role-name-gated.
"""

from __future__ import annotations

import csv
import io
import os
import secrets
import uuid

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.audit import record as audit_record
from ..core.errors import UnauthorizedError, ValidationError
from ..core.logging import get_logger
from ..core.pagination import Page, PageParams, page_params, paginate
from ..core.ratelimit import login_rate_limit
from ..core.storage import get_storage
from ..db.base import get_db
from .deps import get_current_sid, get_current_user, require_permission
from .models import Role, User
from .permissions import PERMISSIONS, CorePerm
from .schemas import (
    AccessOut,
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    ChangePasswordIn,
    ConfirmPasswordIn,
    CreateRoleIn,
    CreateUserIn,
    ForgotPasswordIn,
    LoginIn,
    LoginResult,
    LogoutIn,
    MfaLoginIn,
    PreferencesIn,
    RecoveryCodesOut,
    RefreshIn,
    ResetPasswordIn,
    RoleOut,
    SessionOut,
    SetupIn,
    TokenOut,
    TotpConfirmIn,
    TotpSetupOut,
    TotpStatusOut,
    UpdateMeIn,
    UpdateRoleIn,
    UpdateUserIn,
    UserOut,
)
from .service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


async def _user_out(user: User) -> UserOut:
    """Serialise a User, resolving its avatar_key → a fetchable avatar_url.

    The DB holds a storage *key*; the client needs a *URL*. We resolve it here at
    response time via the storage backend (a stable local URL or a presigned S3
    link), exactly like branding does for its logo. No avatar => avatar_url None.
    """
    out = UserOut.model_validate(user)
    out.avatar_url = await get_storage().url(user.avatar_key) if user.avatar_key else None
    return out


# --- session -----------------------------------------------------------------
def _client_ip(request: Request) -> str | None:
    """Best-effort client IP: first X-Forwarded-For hop if proxied, else peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


@router.get("/setup-status")
async def setup_status(db: AsyncSession = Depends(get_db)) -> dict:
    """PUBLIC — whether the deployment still needs its first administrator."""
    return {"needs_setup": (await AuthService(db).user_count()) == 0}


@router.post("/setup", response_model=TokenOut, status_code=201)
async def setup(
    data: SetupIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    """PUBLIC, one-time — create the first administrator and sign them in.

    Refuses once any user exists, so it can never be used to escalate later.
    """
    svc = AuthService(db)
    admin = await svc.ensure_admin(data.email, data.password, data.full_name or "Administrator")
    if admin is None:
        raise ValidationError("Setup has already been completed.")
    access, refresh = await svc.issue_tokens(
        admin, user_agent=request.headers.get("user-agent"), ip=_client_ip(request)
    )
    await audit_record(
        db, actor=admin, action="auth.setup", target_type="user", target_id=str(admin.id),
    )
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/login", response_model=LoginResult)
async def login(
    data: LoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(login_rate_limit),
) -> LoginResult:
    svc = AuthService(db)
    user = await svc.authenticate(data.email, data.password)
    # First factor passed. If 2FA is on, don't issue tokens yet — challenge for it.
    if user.totp_enabled:
        return LoginResult(mfa_required=True, mfa_token=svc.issue_mfa_challenge(user))
    access, refresh = await svc.issue_tokens(
        user, user_agent=request.headers.get("user-agent"), ip=_client_ip(request)
    )
    await audit_record(
        db, actor=user, action="auth.login", target_type="user", target_id=str(user.id),
    )
    return LoginResult(access_token=access, refresh_token=refresh)


@router.post("/login/mfa", response_model=TokenOut)
async def login_mfa(
    data: MfaLoginIn,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(login_rate_limit),
) -> TokenOut:
    """Second step of a 2FA login: exchange the challenge token + a TOTP/recovery
    code for real access + refresh tokens."""
    svc = AuthService(db)
    user = await svc.verify_mfa_challenge(data.mfa_token, data.code)
    access, refresh = await svc.issue_tokens(
        user, user_agent=request.headers.get("user-agent"), ip=_client_ip(request)
    )
    await audit_record(
        db, actor=user, action="auth.login_mfa", target_type="user", target_id=str(user.id),
    )
    return TokenOut(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=AccessOut)
async def refresh(data: RefreshIn, db: AsyncSession = Depends(get_db)) -> AccessOut:
    return AccessOut(access_token=await AuthService(db).refresh_access(data.refresh_token))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return await _user_out(user)


@router.post("/me/avatar", response_model=UserOut)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """Upload/replace the current user's profile picture (self-service)."""
    from ..settings.service import SettingsService

    if not await SettingsService(db).get("allow_avatar_uploads"):
        raise ValidationError("Profile photo uploads are disabled by the administrator.")
    data = await file.read()
    ext = os.path.splitext(file.filename or "")[1]
    key = f"avatars/{user.id}_{uuid.uuid4().hex}{ext}"
    await get_storage().put(key, data, file.content_type)
    old = user.avatar_key
    updated = await AuthService(db).set_avatar(user, key)
    if old and old != key:  # best-effort cleanup of the previous file
        try:
            await get_storage().delete(old)
        except Exception:  # pragma: no cover - cleanup is best-effort
            get_logger("auth").warning("failed to delete old avatar %s", old, exc_info=True)
    return await _user_out(updated)


@router.delete("/me/avatar", response_model=UserOut)
async def remove_avatar(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """Remove the current user's profile picture (falls back to initials)."""
    old = user.avatar_key
    updated = await AuthService(db).set_avatar(user, None)
    if old:
        try:
            await get_storage().delete(old)
        except Exception:  # pragma: no cover - cleanup is best-effort
            get_logger("auth").warning("failed to delete avatar %s", old, exc_info=True)
    return await _user_out(updated)


@router.patch("/me", response_model=UserOut)
async def update_me(
    data: UpdateMeIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """Self-service: the signed-in user edits their own profile."""
    return await _user_out(await AuthService(db).update_me(user, data))


@router.patch("/me/preferences", response_model=UserOut)
async def update_my_preferences(
    data: PreferencesIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> UserOut:
    """Merge the sent keys into the user's preferences (theme, notifications, …)."""
    return await _user_out(await AuthService(db).set_preferences(user, data.preferences))


@router.get("/me/sessions", response_model=list[SessionOut])
async def list_my_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sid: str | None = Depends(get_current_sid),
) -> list[SessionOut]:
    """The user's live sessions, flagging the one making this request."""
    out: list[SessionOut] = []
    for row in await AuthService(db).list_sessions(user.id):
        s = SessionOut.model_validate(row)
        s.current = sid is not None and str(row.id) == sid
        out.append(s)
    return out


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke_my_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Sign out one of the user's own devices."""
    await AuthService(db).revoke_session(user.id, session_id)


@router.post("/me/sessions/revoke-others", status_code=204)
async def revoke_my_other_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sid: str | None = Depends(get_current_sid),
) -> None:
    """Sign out everywhere except the current device."""
    keep = uuid.UUID(sid) if sid else None
    await AuthService(db).revoke_other_sessions(user.id, keep)


@router.post("/logout", status_code=204)
async def logout(
    data: LogoutIn,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> None:
    await AuthService(db).logout(data.refresh_token)


@router.post("/change-password", status_code=204)
async def change_password(
    data: ChangePasswordIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    await AuthService(db).change_password(user, data.current_password, data.new_password)


# --- two-factor auth (self-service) ------------------------------------------
@router.get("/me/2fa", response_model=TotpStatusOut)
async def two_factor_status(user: User = Depends(get_current_user)) -> TotpStatusOut:
    return TotpStatusOut(
        enabled=user.totp_enabled,
        recovery_codes_remaining=len(user.mfa_recovery_codes or []),
    )


@router.post("/me/2fa/setup", response_model=TotpSetupOut)
async def two_factor_setup(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TotpSetupOut:
    """Begin 2FA enrolment: returns the secret + otpauth URI to show as a QR code.
    Not active until confirmed with a valid code."""
    secret, uri = await AuthService(db).begin_totp_setup(user)
    return TotpSetupOut(secret=secret, otpauth_uri=uri)


@router.post("/me/2fa/confirm", response_model=RecoveryCodesOut)
async def two_factor_confirm(
    data: TotpConfirmIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecoveryCodesOut:
    """Verify the first code, enable 2FA, and return one-time recovery codes."""
    codes = await AuthService(db).confirm_totp_setup(user, data.code)
    await audit_record(
        db, actor=user, action="auth.2fa_enable", target_type="user", target_id=str(user.id),
    )
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/me/2fa/disable", status_code=204)
async def two_factor_disable(
    data: TotpConfirmIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """Turn off 2FA (requires a current TOTP or a recovery code)."""
    await AuthService(db).disable_totp(user, data.code)
    await audit_record(
        db, actor=user, action="auth.2fa_disable", target_type="user", target_id=str(user.id),
    )


@router.post("/me/2fa/recovery-codes", response_model=RecoveryCodesOut)
async def two_factor_recovery_codes(
    data: TotpConfirmIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecoveryCodesOut:
    """Regenerate recovery codes (invalidates the old set)."""
    codes = await AuthService(db).regenerate_recovery_codes(user, data.code)
    return RecoveryCodesOut(recovery_codes=codes)


@router.post("/forgot-password")
async def forgot_password(data: ForgotPasswordIn, db: AsyncSession = Depends(get_db)) -> dict:
    result = await AuthService(db).request_password_reset(data.email)
    if result is not None:
        user, raw = result
        from ..messaging.email import send_email

        html = (
            "<p>You requested a password reset. Use this token to set a new password "
            f"(valid 1 hour):</p><p><code>{raw}</code></p>"
        )
        await send_email(db, [user.email], "Reset your password", html)
    # Always 200 — never reveal whether the email is registered.
    return {"status": "ok"}


@router.post("/reset-password", status_code=204)
async def reset_password(data: ResetPasswordIn, db: AsyncSession = Depends(get_db)) -> None:
    await AuthService(db).reset_password(data.token, data.new_password)


# --- permission catalog (for the role editor UI) -----------------------------
@router.get("/permissions")
async def permissions(_: User = Depends(require_permission(CorePerm.ROLE_READ))) -> dict:
    return {"groups": PERMISSIONS.grouped()}


# --- roles (dynamic RBAC) ----------------------------------------------------
@router.post("/roles", response_model=RoleOut, status_code=201)
async def create_role(
    data: CreateRoleIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.ROLE_MANAGE)),
):
    role = await AuthService(db).create_role(data)
    await audit_record(
        db, actor=actor, action="role.create", target_type="role",
        target_id=str(role.id), meta={"name": role.name},
    )
    return role


@router.get("/roles", response_model=Page[RoleOut])
async def list_roles(
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.ROLE_READ)),
):
    return await paginate(db, AuthService(db).roles_query(), params, item_model=RoleOut)


@router.patch("/roles/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: uuid.UUID,
    data: UpdateRoleIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.ROLE_MANAGE)),
):
    role = await AuthService(db).update_role(role_id, data)
    await audit_record(
        db, actor=actor, action="role.update", target_type="role",
        target_id=str(role_id), meta={"name": role.name},
    )
    return role


@router.delete("/roles/{role_id}", status_code=204)
async def delete_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.ROLE_MANAGE)),
) -> None:
    await AuthService(db).delete_role(role_id)
    await audit_record(
        db, actor=actor, action="role.delete", target_type="role", target_id=str(role_id),
    )


# --- users -------------------------------------------------------------------
@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    data: CreateUserIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.USER_MANAGE)),
) -> UserOut:
    user = await AuthService(db).create_user(data)
    await audit_record(
        db, actor=actor, action="user.create", target_type="user",
        target_id=str(user.id), meta={"email": user.email},
    )
    if data.send_invite:
        await _send_invite_email(db, user)
    return await _user_out(user)


async def _send_invite_email(db: AsyncSession, user: User) -> None:
    """Email the new user a welcome + secure 'set your password' activation link.
    Reuses the password-reset token, so clicking it both verifies their inbox and
    lets them choose a password. Best-effort: a mail failure won't fail user creation.
    """
    from ..branding import service as branding_service
    from ..core.config import get_settings
    from ..messaging import templates as email_templates
    from ..messaging.email import send_email

    try:
        res = await AuthService(db).request_password_reset(user.email)
        if res is None:
            return
        _, raw = res
        settings = get_settings()
        activate_url = f"{settings.frontend_url.rstrip('/')}/forgot-password?token={raw}"
        branding = await branding_service.get_or_create(db)
        ctx = {
            "name": user.full_name or user.email,
            "app_name": branding.app_name,
            "activate_url": activate_url,
        }
        subject, body = await email_templates.render_with_overrides(db, "welcome", ctx)
        html = email_templates.wrap_email(branding.app_name, body)
        await send_email(db, [user.email], subject, html)
    except Exception:  # pragma: no cover - invites are best-effort
        get_logger("auth").warning("invite email failed for %s", user.email, exc_info=True)


@router.get("/users", response_model=Page[UserOut])
async def list_users(
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.USER_READ)),
) -> Page[UserOut]:
    page = await paginate(db, AuthService(db).users_query(), params)
    page.items = [await _user_out(u) for u in page.items]
    return page


@router.get("/users/export")
async def export_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.USER_READ)),
) -> StreamingResponse:
    """Download all users as a CSV (email, name, role, status, verified, last login)."""
    rows = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["email", "full_name", "role", "is_active", "email_verified", "last_login_at"])
    for u in rows:
        writer.writerow(
            [
                u.email,
                u.full_name or "",
                u.role.name if u.role else "",
                u.is_active,
                u.email_verified,
                u.last_login_at.isoformat() if u.last_login_at else "",
            ]
        )
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@router.post("/users/import")
async def import_users(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.USER_MANAGE)),
) -> dict:
    """Bulk-create users from a CSV.

    Columns: ``email`` (required), ``full_name``, ``role`` (role name; falls back to
    the caller's role), ``send_invite`` (default true). When no password column is
    given, a random one is set and the user is invited to choose their own.
    """
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    roles = (await db.execute(select(Role))).scalars().all()
    role_by_name = {r.name.lower(): r for r in roles}

    created, skipped, errors = 0, 0, []
    svc = AuthService(db)
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        email = (row.get("email") or "").strip()
        if not email:
            continue
        role_name = (row.get("role") or "").strip().lower()
        role = role_by_name.get(role_name) or actor.role
        send_invite = _truthy(row.get("send_invite", "true"))
        password = (row.get("password") or "").strip() or (secrets.token_urlsafe(10) + "aA1")
        try:
            user = await svc.create_user(
                CreateUserIn(
                    email=email,
                    password=password,
                    full_name=(row.get("full_name") or "").strip() or None,
                    role_id=role.id,
                    send_invite=send_invite,
                )
            )
            if send_invite:
                await _send_invite_email(db, user)
            created += 1
        except Exception as exc:  # duplicate email, bad data, …
            skipped += 1
            errors.append({"row": i, "email": email, "error": str(exc)})

    await audit_record(
        db, actor=actor, action="user.import", target_type="user", target_id="bulk",
        meta={"created": created, "skipped": skipped},
    )
    return {"created": created, "skipped": skipped, "errors": errors[:20]}


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    data: UpdateUserIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.USER_MANAGE)),
) -> UserOut:
    user = await AuthService(db).update_user(user_id, data)
    await audit_record(
        db, actor=actor, action="user.update", target_type="user",
        target_id=str(user_id), meta=data.model_dump(exclude_none=True),
    )
    return await _user_out(user)


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    data: ConfirmPasswordIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.USER_MANAGE)),
) -> None:
    """Delete a user. Requires the acting admin to re-enter their own password,
    and blocks deleting your own account."""
    if actor.id == user_id:
        raise ValidationError("You cannot delete your own account.")
    svc = AuthService(db)
    if not svc.verify_actor_password(actor, data.password):
        raise UnauthorizedError("Password confirmation failed.")
    user = await svc.delete_user(user_id)
    await audit_record(
        db, actor=actor, action="user.delete", target_type="user",
        target_id=str(user_id), meta={"email": user.email},
    )


# --- API keys ----------------------------------------------------------------
@router.post("/api-keys", response_model=ApiKeyCreatedOut, status_code=201)
async def create_api_key(
    data: ApiKeyCreateIn,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.APIKEY_MANAGE)),
) -> ApiKeyCreatedOut:
    key, raw = await AuthService(db).create_api_key(data)
    await audit_record(
        db, actor=actor, action="apikey.create", target_type="api_key",
        target_id=str(key.id), meta={"name": key.name},
    )
    return ApiKeyCreatedOut(**ApiKeyOut.model_validate(key).model_dump(), key=raw)


@router.get("/api-keys", response_model=Page[ApiKeyOut])
async def list_api_keys(
    params: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_permission(CorePerm.APIKEY_MANAGE)),
) -> Page[ApiKeyOut]:
    return await paginate(db, AuthService(db).api_keys_query(), params, item_model=ApiKeyOut)


@router.delete("/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_permission(CorePerm.APIKEY_MANAGE)),
) -> None:
    await AuthService(db).revoke_api_key(key_id)
    await audit_record(
        db, actor=actor, action="apikey.revoke", target_type="api_key", target_id=str(key_id),
    )
