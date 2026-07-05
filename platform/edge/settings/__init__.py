"""System settings module: admin-editable key/value config + public read."""

from .models import AppSetting
from .router import router

__all__ = ["router", "AppSetting"]
