"""AuthService — all auth business logic (DB writes commit explicitly).

Handles authentication, dynamic role CRUD, users, and API keys. Kept separate from
the router so it is unit-testable and reusable (CLI, startup bootstrap).
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from .models import ApiKey, PasswordResetToken, RefreshToken, Role, User
from .permissions import PERMISSIONS, WILDCARD
from .schemas import (
    ApiKeyCreateIn,
    CreateRoleIn,
    CreateUserIn,
    UpdateMeIn,
    UpdateRoleIn,
    UpdateUserIn,
)
from .security import (
    REFRESH_TTL,
    create_access_token,
    create_mfa_challenge_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    generate_recovery_codes,
    generate_reset_token,
    generate_totp_secret,
    hash_api_key,
    hash_password,
    normalize_recovery_code,
    totp_provisioning_uri,
    validate_password,
    verify_password,
    verify_totp,
)

RESET_TTL = dt.timedelta(hours=1)

ADMIN_ROLE_NAME = "Administrator"


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime) -> dt.datetime:
    """Coerce a DB datetime to UTC-aware (SQLite returns naive; Postgres aware)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=dt.timezone.utc)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- authentication ----------------------------------------------------
    async def authenticate(self, email: str, password: str) -> User:
        from ..core.config import get_settings

        settings = get_settings()
        user = (
            await self.db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            raise UnauthorizedError("invalid email or password")
        # Per-account lockout: reject while locked (don't even check the password).
        if user.locked_until is not None and _aware(user.locked_until) > _now():
            raise UnauthorizedError("account temporarily locked after failed logins; try again later")
        if not verify_password(password, user.password_hash):
            user.failed_login_count = (user.failed_login_count or 0) + 1
            if (
                settings.lockout_max_attempts > 0
                and settings.lockout_minutes > 0
                and user.failed_login_count >= settings.lockout_max_attempts
            ):
                user.locked_until = _now() + dt.timedelta(minutes=settings.lockout_minutes)
            await self.db.commit()
            raise UnauthorizedError("invalid email or password")
        # Success — clear the lockout counters and stamp the login.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = _now()
        await self.db.commit()
        return user

    def _set_password(self, user: User, new: str) -> None:
        """Validate + apply a new password with reuse-prevention + timestamping.

        Blocks reuse of the current or last N passwords (config), records the
        change time (for expiry), and clears the force-change flag.
        """
        from ..core.config import get_settings

        validate_password(new)
        n = get_settings().password_history_count
        if n > 0:
            history = list(user.password_history or [])
            if verify_password(new, user.password_hash) or any(
                verify_password(new, h) for h in history
            ):
                raise ValidationError("password was used recently — choose a different one")
            history.insert(0, user.password_hash)  # archive the outgoing hash
            user.password_history = history[:n]
        user.password_hash = hash_password(new)
        user.password_changed_at = _now()
        user.must_change_password = False

    async def issue_tokens(
        self, user: User, *, user_agent: str | None = None, ip: str | None = None
    ) -> tuple[str, str]:
        """Issue an access token + a REVOCABLE refresh token (persisted by jti).

        The refresh token row doubles as a "session": it records the device
        (user_agent) and ip so the user can review and revoke it later.
        """
        jti = uuid.uuid4()
        self.db.add(
            RefreshToken(
                id=jti,
                user_id=user.id,
                expires_at=_now() + REFRESH_TTL,
                user_agent=user_agent,
                ip=ip,
                last_used_at=_now(),
            )
        )
        await self.db.commit()
        return create_access_token(user, sid=str(jti)), create_refresh_token(user, str(jti))

    async def refresh_access(self, refresh_token: str) -> str:
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError:
            raise UnauthorizedError("invalid or expired refresh token")
        if payload.get("type") != "refresh":
            raise UnauthorizedError("not a refresh token")
        jti = payload.get("jti")
        row = await self.db.get(RefreshToken, uuid.UUID(jti)) if jti else None
        if row is None or row.revoked_at is not None or _aware(row.expires_at) <= _now():
            raise UnauthorizedError("refresh token is invalid, expired, or revoked")
        user = await self.db.get(User, uuid.UUID(payload["sub"]))
        if user is None or not user.is_active:
            raise UnauthorizedError("user not found or inactive")
        # Touch the session so "last active" stays fresh in the sessions list.
        row.last_used_at = _now()
        await self.db.commit()
        return create_access_token(user, sid=str(row.id))

    async def logout(self, refresh_token: str) -> None:
        """Revoke a single refresh token (idempotent; silently ignores bad tokens)."""
        try:
            payload = decode_token(refresh_token)
        except jwt.PyJWTError:
            return
        jti = payload.get("jti")
        row = await self.db.get(RefreshToken, uuid.UUID(jti)) if jti else None
        if row is not None and row.revoked_at is None:
            row.revoked_at = _now()
            await self.db.commit()

    async def revoke_all_refresh(self, user_id: uuid.UUID) -> None:
        """Revoke every live refresh token for a user (used after a password change)."""
        rows = (
            await self.db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
                )
            )
        ).scalars().all()
        for row in rows:
            row.revoked_at = _now()
        await self.db.commit()

    async def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise UnauthorizedError("current password is incorrect")
        self._set_password(user, new)
        await self.db.commit()
        await self.revoke_all_refresh(user.id)  # force re-login on other devices

    async def request_password_reset(self, email: str) -> tuple[User, str] | None:
        """Create a reset token if the email maps to an active user. Returns
        (user, raw_token) for the caller to email, or None (caller replies 200 either
        way so attackers can't probe which emails exist)."""
        user = (
            await self.db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if user is None or not user.is_active:
            return None
        raw, token_hash = generate_reset_token()
        self.db.add(
            PasswordResetToken(user_id=user.id, token_hash=token_hash, expires_at=_now() + RESET_TTL)
        )
        await self.db.commit()
        return user, raw

    async def reset_password(self, token: str, new: str) -> None:
        row = (
            await self.db.execute(
                select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_api_key(token))
            )
        ).scalar_one_or_none()
        if row is None or row.used_at is not None or _aware(row.expires_at) <= _now():
            raise ValidationError("invalid or expired reset token")
        user = await self.db.get(User, row.user_id)
        self._set_password(user, new)
        # Completing an emailed reset/invite link proves the user controls the inbox.
        user.email_verified = True
        # A successful reset also clears any brute-force lockout.
        user.failed_login_count = 0
        user.locked_until = None
        row.used_at = _now()
        await self.db.commit()
        await self.revoke_all_refresh(user.id)

    # --- two-factor auth (TOTP) -------------------------------------------
    def _check_mfa(self, user: User, code: str) -> bool:
        """True if ``code`` is a valid TOTP OR an unused recovery code.

        A matching recovery code is CONSUMED (removed from the list) as a side
        effect — the caller is responsible for committing the session.
        """
        from ..core.secrets import decrypt_secret

        if user.totp_secret and verify_totp(decrypt_secret(user.totp_secret), code):
            return True
        target = hash_api_key(normalize_recovery_code(code))
        codes = list(user.mfa_recovery_codes or [])
        if target in codes:
            codes.remove(target)
            user.mfa_recovery_codes = codes
            return True
        return False

    def issue_mfa_challenge(self, user: User) -> str:
        """First factor passed but 2FA is on — hand back a short-lived challenge
        token the client exchanges (with a TOTP/recovery code) for real tokens."""
        return create_mfa_challenge_token(user)

    async def verify_mfa_challenge(self, mfa_token: str, code: str) -> User:
        try:
            payload = decode_token(mfa_token)
        except jwt.PyJWTError:
            raise UnauthorizedError("invalid or expired 2FA session")
        if payload.get("type") != "mfa":
            raise UnauthorizedError("not a 2FA token")
        user = await self.db.get(User, uuid.UUID(payload["sub"]))
        if user is None or not user.is_active or not user.totp_enabled:
            raise UnauthorizedError("2FA session is no longer valid")
        if not self._check_mfa(user, code):
            raise UnauthorizedError("invalid authentication or recovery code")
        await self.db.commit()  # persist a consumed recovery code
        return user

    async def begin_totp_setup(self, user: User) -> tuple[str, str]:
        """Generate + stash a new (still-disabled) TOTP secret; return
        (secret, otpauth_uri) for the client to show as text + QR."""
        from ..core.config import get_settings
        from ..core.secrets import encrypt_secret

        secret = generate_totp_secret()
        user.totp_secret = encrypt_secret(secret)
        user.totp_enabled = False
        await self.db.commit()
        issuer = get_settings().app_name or "Vizor"
        return secret, totp_provisioning_uri(secret, user.email, issuer)

    async def confirm_totp_setup(self, user: User, code: str) -> list[str]:
        """Verify the first code against the pending secret, enable 2FA, and
        return freshly generated one-time recovery codes (shown once)."""
        from ..core.secrets import decrypt_secret

        if not user.totp_secret or user.totp_enabled:
            raise ValidationError("no pending 2FA setup — start setup first")
        if not verify_totp(decrypt_secret(user.totp_secret), code):
            raise ValidationError("invalid authentication code")
        user.totp_enabled = True
        raw, hashed = generate_recovery_codes()
        user.mfa_recovery_codes = hashed
        await self.db.commit()
        return raw

    async def disable_totp(self, user: User, code: str) -> None:
        if not user.totp_enabled:
            return
        if not self._check_mfa(user, code):
            raise UnauthorizedError("invalid authentication or recovery code")
        user.totp_enabled = False
        user.totp_secret = None
        user.mfa_recovery_codes = []
        await self.db.commit()

    async def regenerate_recovery_codes(self, user: User, code: str) -> list[str]:
        if not user.totp_enabled:
            raise ValidationError("2FA is not enabled")
        if not self._check_mfa(user, code):
            raise UnauthorizedError("invalid authentication or recovery code")
        raw, hashed = generate_recovery_codes()
        user.mfa_recovery_codes = hashed
        await self.db.commit()
        return raw

    # --- roles (dynamic RBAC) ---------------------------------------------
    async def create_role(self, data: CreateRoleIn) -> Role:
        unknown = PERMISSIONS.unknown(data.permissions)
        if unknown:
            raise ValidationError(f"unknown permissions: {unknown}")
        if WILDCARD in data.permissions:
            raise ValidationError("wildcard '*' is reserved for the system Administrator role")
        if await self._role_by_name(data.name):
            raise ConflictError("a role with this name already exists")
        role = Role(name=data.name, description=data.description, permissions=list(data.permissions))
        self.db.add(role)
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def update_role(self, role_id: uuid.UUID, data: UpdateRoleIn) -> Role:
        role = await self.db.get(Role, role_id)
        if role is None:
            raise NotFoundError("role not found")
        if role.is_system:
            raise ValidationError("the system Administrator role cannot be modified")
        if data.permissions is not None:
            unknown = PERMISSIONS.unknown(data.permissions)
            if unknown:
                raise ValidationError(f"unknown permissions: {unknown}")
            if WILDCARD in data.permissions:
                raise ValidationError("wildcard '*' is reserved for the system role")
            role.permissions = list(data.permissions)
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        await self.db.commit()
        await self.db.refresh(role)
        return role

    async def delete_role(self, role_id: uuid.UUID) -> None:
        role = await self.db.get(Role, role_id)
        if role is None:
            raise NotFoundError("role not found")
        if role.is_system:
            raise ValidationError("the system Administrator role cannot be deleted")
        in_use = await self.db.scalar(
            select(func.count()).select_from(User).where(User.role_id == role_id)
        )
        if in_use:
            raise ConflictError("role is assigned to users; reassign them first")
        await self.db.delete(role)
        await self.db.commit()

    def roles_query(self):
        return select(Role).order_by(Role.name)

    async def _role_by_name(self, name: str) -> Role | None:
        return (
            await self.db.execute(select(Role).where(Role.name == name))
        ).scalar_one_or_none()

    async def _require_role(self, role_id: uuid.UUID) -> Role:
        role = await self.db.get(Role, role_id)
        if role is None:
            raise ValidationError("role_id does not reference an existing role")
        return role

    # --- users -------------------------------------------------------------
    async def create_user(self, data: CreateUserIn) -> User:
        if (await self.db.execute(select(User).where(User.email == data.email))).scalar_one_or_none():
            raise ConflictError("email already registered")
        validate_password(data.password)
        await self._require_role(data.role_id)
        user = User(
            email=data.email,
            full_name=data.full_name,
            role_id=data.role_id,
            password_hash=hash_password(data.password),
            is_active=True if data.is_active is None else data.is_active,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_user(self, user_id: uuid.UUID, data: UpdateUserIn) -> User:
        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        if data.role_id is not None:
            await self._require_role(data.role_id)
            user.role_id = data.role_id
        if data.is_active is not None:
            user.is_active = data.is_active
        if data.full_name is not None:
            user.full_name = data.full_name
        await self.db.commit()
        await self.db.refresh(user)
        return user

    def users_query(self):
        return select(User).order_by(User.created_at.desc())

    async def delete_user(self, user_id: uuid.UUID) -> User:
        """Hard-delete a user. Refresh/reset tokens cascade automatically."""
        user = await self.db.get(User, user_id)
        if user is None:
            raise NotFoundError("user not found")
        await self.db.delete(user)
        await self.db.commit()
        return user

    def verify_actor_password(self, actor: User, password: str) -> bool:
        """Confirm the acting admin re-entered their own password (for sensitive ops)."""
        return verify_password(password, actor.password_hash)

    async def set_avatar(self, user: User, key: str | None) -> User:
        """Point a user at a new avatar storage key (or None to clear it)."""
        user.avatar_key = key
        await self.db.commit()
        await self.db.refresh(user)
        return user

    # --- self-service account -------------------------------------------------
    async def update_me(self, user: User, data: UpdateMeIn) -> User:
        """Let the signed-in user edit their own profile (name for now)."""
        if data.full_name is not None:
            user.full_name = data.full_name
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def set_preferences(self, user: User, prefs: dict) -> User:
        """Shallow-merge ``prefs`` into the user's preferences (only sent keys change)."""
        user.preferences = {**(user.preferences or {}), **prefs}
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def list_sessions(self, user_id: uuid.UUID) -> list[RefreshToken]:
        """Live (non-revoked) sessions for a user, most-recently-active first."""
        rows = (
            await self.db.execute(
                select(RefreshToken)
                .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
                .order_by(RefreshToken.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        """Revoke one of the user's own sessions (idempotent)."""
        row = await self.db.get(RefreshToken, session_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError("session not found")
        if row.revoked_at is None:
            row.revoked_at = _now()
            await self.db.commit()

    async def revoke_other_sessions(self, user_id: uuid.UUID, keep_id: uuid.UUID | None) -> int:
        """Revoke all of a user's sessions except ``keep_id``. Returns the count."""
        rows = (
            await self.db.execute(
                select(RefreshToken).where(
                    RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
                )
            )
        ).scalars().all()
        n = 0
        for row in rows:
            if keep_id is not None and row.id == keep_id:
                continue
            row.revoked_at = _now()
            n += 1
        if n:
            await self.db.commit()
        return n

    # --- bootstrap ---------------------------------------------------------
    async def user_count(self) -> int:
        return int(await self.db.scalar(select(func.count()).select_from(User)) or 0)

    async def ensure_admin(
        self, email: str, password: str, full_name: str = "Administrator"
    ) -> User | None:
        """Create the built-in Administrator role + first admin if there are no users.

        Idempotent and race-safe: under a multi-worker server (gunicorn), every worker
        runs this at startup, so the "no users yet" check is a classic TOCTOU — all
        workers pass it and race to INSERT. The loser hits a unique-violation; we catch
        it, roll back, and treat the admin as already provisioned (return None) instead
        of crashing the worker on boot.
        """
        if await self.db.scalar(select(func.count()).select_from(User)):
            return None
        try:
            role = await self._role_by_name(ADMIN_ROLE_NAME)
            if role is None:
                role = Role(
                    name=ADMIN_ROLE_NAME,
                    description="Full access (system role)",
                    permissions=[WILDCARD],
                    is_system=True,
                )
                self.db.add(role)
                await self.db.commit()
                await self.db.refresh(role)
            admin = await self.create_user(
                CreateUserIn(
                    email=email, password=password, full_name=full_name or "Administrator",
                    role_id=role.id,
                )
            )
            # The bootstrap admin is trusted — mark it verified.
            admin.email_verified = True
            await self.db.commit()
            await self.db.refresh(admin)
            return admin
        except IntegrityError:
            # Another worker won the first-boot bootstrap race → already provisioned.
            await self.db.rollback()
            return None

    # --- API keys ----------------------------------------------------------
    async def create_api_key(self, data: ApiKeyCreateIn) -> tuple[ApiKey, str]:
        await self._require_role(data.role_id)
        raw, prefix, key_hash = generate_api_key()
        key = ApiKey(name=data.name, role_id=data.role_id, prefix=prefix, key_hash=key_hash)
        self.db.add(key)
        await self.db.commit()
        await self.db.refresh(key)
        return key, raw

    def api_keys_query(self):
        return select(ApiKey).order_by(ApiKey.created_at.desc())

    async def revoke_api_key(self, key_id: uuid.UUID) -> None:
        key = await self.db.get(ApiKey, key_id)
        if key is None:
            raise NotFoundError("api key not found")
        key.is_active = False
        await self.db.commit()
