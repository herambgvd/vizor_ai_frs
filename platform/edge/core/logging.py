"""Structured logging + per-request correlation.

Why this exists: in a real deployment you must be able to answer "what happened
to request X?". So every log line carries a **request id**, and one line is
emitted per HTTP request with method, path, status, and latency.

  configure_logging(env)      one-time setup. Human-readable in dev, JSON in prod
                              (prod logs are machine-ingestible: ELK/Loki/etc.).
  get_logger(name)            module logger; use instead of print().
  RequestLoggingMiddleware    assigns/propagates the request id + access log line.

The request id flows via a contextvar so ANY log call during a request is tagged,
even deep in a service with no access to the request object.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Holds the current request's id; "-" outside a request (startup, workers).
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Injects the current request id onto every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        return True


class _JsonFormatter(logging.Formatter):
    """One JSON object per line — for prod log ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(env: str = "dev", level: int = logging.INFO) -> None:
    """Install a single root handler. Safe to call once at startup."""
    handler = logging.StreamHandler()
    handler.addFilter(_RequestIdFilter())
    if env == "dev":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s [%(request_id)s] %(name)s: %(message)s")
        )
    else:
        handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]  # replace, don't stack, on re-config
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Per-request id + access log. Add this OUTERMOST so it times everything."""

    async def dispatch(self, request: Request, call_next):
        # Honour an inbound X-Request-ID (e.g. from a gateway) or mint one.
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(rid)
        log = get_logger("edge.request")
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            # request_id is reset in finally so it never leaks between requests.
            pass
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "%s %s -> %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = rid
        request_id_ctx.reset(token)
        return response
