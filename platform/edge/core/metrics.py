"""Prometheus metrics: request count + latency, exposed at /metrics.

Scrape http://<host>/metrics with Prometheus. Paths are labelled by the matched
ROUTE TEMPLATE (e.g. /api/v1/users/{user_id}) — not the concrete URL — so IDs
don't explode metric cardinality.
"""

from __future__ import annotations

import time

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUESTS = Counter(
    "edge_http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
LATENCY = Histogram(
    "edge_http_request_duration_seconds", "HTTP request latency (s)", ["method", "path"]
)


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        path = _route_template(request)  # populated after routing
        LATENCY.labels(request.method, path).observe(time.perf_counter() - start)
        REQUESTS.labels(request.method, path, response.status_code).inc()
        return response


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
