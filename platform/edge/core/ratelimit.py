"""Lightweight in-memory sliding-window rate limiter (per key).

Used to throttle login attempts (brute-force protection). SINGLE-PROCESS only —
each worker keeps its own window; for a multi-worker deployment back this with
Redis (settings.redis_url). Good enough as a first line of defence and for dev.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Request

from .config import get_settings
from .errors import AppError

_hits: dict[str, deque] = defaultdict(deque)


class RateLimitError(AppError):
    code = "RATE_LIMITED"
    status_code = 429


def hit(key: str, limit: int, window: float = 60.0) -> None:
    """Record a hit for ``key``; raise RateLimitError if over ``limit`` per window."""
    now = time.monotonic()
    bucket = _hits[key]
    cutoff = now - window
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        raise RateLimitError("too many requests — please try again shortly")
    bucket.append(now)


def login_rate_limit(request: Request) -> None:
    """FastAPI dependency: throttle login by client IP."""
    ip = request.client.host if request.client else "unknown"
    hit(f"login:{ip}", get_settings().rate_limit_login_per_minute, 60.0)
