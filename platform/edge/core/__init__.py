"""Core: config, licensing, module registry, app factory, errors, logging, pagination."""

from .api import create_app
from .config import Settings, get_settings
from .errors import (
    AppError,
    ConflictError,
    ForbiddenError,
    LicenseLimitError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
    register_error_handlers,
)
from .license import License, LicenseError, load_license, verify_license
from .logging import configure_logging, get_logger
from .modules import ModuleRegistry, ModuleSpec
from .pagination import Page, PageParams, page_params, paginate
from .realtime import RealtimeHub, hub
from .secrets import decrypt_secret, encrypt_secret
from .storage import Storage, get_storage

__all__ = [
    # app factory + config
    "create_app",
    "Settings",
    "get_settings",
    # licensing
    "License",
    "LicenseError",
    "load_license",
    "verify_license",
    # feature modules
    "ModuleRegistry",
    "ModuleSpec",
    # errors
    "AppError",
    "NotFoundError",
    "ValidationError",
    "ConflictError",
    "UnauthorizedError",
    "ForbiddenError",
    "LicenseLimitError",
    "register_error_handlers",
    # logging
    "configure_logging",
    "get_logger",
    # secrets
    "encrypt_secret",
    "decrypt_secret",
    # storage
    "Storage",
    "get_storage",
    # realtime
    "RealtimeHub",
    "hub",
    # pagination
    "Page",
    "PageParams",
    "page_params",
    "paginate",
]
