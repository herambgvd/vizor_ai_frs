"""License status + update endpoints.

  GET  /api/license   → current status (client, expiry, is_expired, limits, modules).
                        Reachable even when expired so the frontend can show the banner.
  POST /api/license   → upload a new signed token (admin, settings.manage). Verified
                        against the bundled public key; an already-expired token is
                        rejected. On success the running app switches to it immediately.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from ..auth.deps import get_current_user, require_permission
from ..auth.permissions import CorePerm
from ..core.config import Settings, get_settings
from ..core.errors import ValidationError
from ..core.license import LicenseError, verify_license

router = APIRouter(prefix="/license", tags=["license"])


class LicenseUpdateIn(BaseModel):
    token: str


def _status(lic) -> dict:
    return {
        "client": lic.client,
        "expires_at": lic.expires_at.isoformat() if lic.expires_at else None,
        "is_expired": lic.is_expired,
        "modules": sorted(lic.modules),
        "limits": {} if lic._dev else lic.limits,
        "features": {} if lic._dev else lic.features,
        "dev": lic._dev,
    }


def _public_key(settings: Settings) -> str | None:
    if settings.license_public_key:
        return settings.license_public_key
    if settings.license_public_key_file:
        p = Path(settings.license_public_key_file)
        if p.exists():
            return p.read_text()
    return None


@router.get("")
async def license_status(request: Request, _user=Depends(get_current_user)) -> dict:
    return _status(request.app.state.license)


@router.post("")
async def update_license(
    data: LicenseUpdateIn,
    request: Request,
    _=Depends(require_permission(CorePerm.SETTINGS_MANAGE)),
) -> dict:
    settings = get_settings()
    public_key = _public_key(settings)
    if not public_key:
        raise ValidationError("no license public key configured to verify against")
    try:
        new_license = verify_license(data.token, public_key)
    except LicenseError as exc:
        raise ValidationError(f"invalid license: {exc}")
    if new_license.is_expired:
        raise ValidationError("this license is already expired")

    # Persist so it survives a restart; the in-memory switch applies either way.
    target = settings.license_token_file or "license.jwt"
    try:
        Path(target).write_text(data.token)
    except OSError:
        pass
    request.app.state.license = new_license
    return _status(new_license)
