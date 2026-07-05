"""Auth: users, JWT (access/refresh), dynamic RBAC (roles + permissions), API keys.

Wire into a scenario app:

    from edge.core import create_app, ModuleRegistry
    from edge import auth
    app = create_app(registry, extra_routers=[auth.router])

Protect a route by PERMISSION (not role name):

    @router.post("/cameras")
    async def add_camera(user = Depends(auth.require_permission("camera.create"))):
        ...

A feature module contributes permissions to the catalog:

    from edge.auth import PERMISSIONS, Permission
    PERMISSIONS.register(Permission("camera.create", "Add cameras", "Cameras"))
"""

from .deps import get_api_key, get_current_user, require_permission, user_has
from .models import ApiKey, Role, User
from .permissions import PERMISSIONS, CorePerm, Permission, PermissionRegistry
from .router import router
from .service import AuthService

__all__ = [
    "router",
    "AuthService",
    "get_current_user",
    "get_api_key",
    "require_permission",
    "user_has",
    "PERMISSIONS",
    "Permission",
    "PermissionRegistry",
    "CorePerm",
    "Role",
    "User",
    "ApiKey",
]
