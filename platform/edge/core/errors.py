"""Uniform error handling: one JSON envelope + stable machine-readable codes.

Every error the API returns has the SAME shape, so clients never have to guess:

    { "error": {
        "code": "CAMERA_LIMIT_EXCEEDED",   # stable — clients switch on this
        "message": "Camera limit reached (10).",  # human — safe to show in UI
        "details": { ... }                 # optional structured context
    } }

Usage in a route/service — just raise:

    raise NotFoundError("camera not found")
    raise LicenseLimitError("camera limit reached", details={"limit": 10})

The handlers registered by ``register_error_handlers(app)`` turn any AppError into
the envelope above. FastAPI validation errors and Starlette HTTPExceptions are
normalised into the same shape. Anything unexpected becomes a safe 500
``INTERNAL_ERROR`` (internals hidden) and is logged with the request id.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging import get_logger

log = get_logger("edge.error")


class AppError(Exception):
    """Base class for all application errors. Subclass, or raise directly.

    Attributes come from the class (subclass defaults) but can be overridden
    per-instance for one-off cases.
    """

    code: str = "ERROR"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.details = details


# --- Common, reusable error types (stable codes shared by every scenario) ----
class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = status.HTTP_404_NOT_FOUND


class ValidationError(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422  # Unprocessable (literal — constant name varies across Starlette versions)


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = status.HTTP_409_CONFLICT


class UnauthorizedError(AppError):
    code = "UNAUTHORIZED"
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AppError):
    code = "FORBIDDEN"
    status_code = status.HTTP_403_FORBIDDEN


class LicenseLimitError(AppError):
    """A license limit was hit (cameras, storage, or a disabled module)."""

    code = "LICENSE_LIMIT"
    status_code = status.HTTP_409_CONFLICT


class LicenseExpiredError(AppError):
    """The license has expired — platform access is blocked until it is renewed."""

    code = "LICENSE_EXPIRED"
    status_code = status.HTTP_403_FORBIDDEN


# Map raw HTTP status codes (from Starlette/FastAPI HTTPException) to our codes.
_HTTP_CODE_MAP = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def _envelope(code: str, message: str, details: Any | None = None) -> dict:
    body: dict = {"error": {"code": code, "message": message}}
    if details is not None:
        body["error"]["details"] = details
    return body


def register_error_handlers(app: FastAPI) -> None:
    """Attach the four handlers that produce the uniform error envelope."""

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_envelope(
                "VALIDATION_ERROR",
                "Request validation failed",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODE_MAP.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to the client; log the full trace with request id.
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope("INTERNAL_ERROR", "An unexpected error occurred"),
        )
