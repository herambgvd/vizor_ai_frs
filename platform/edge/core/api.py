"""FastAPI application factory shared by every scenario app.

    from edge.core import create_app, ModuleRegistry
    registry = ModuleRegistry()
    registry.register(cameras.SPEC).register(attendance.SPEC)  # etc.
    app = create_app(registry, title="Vizor FRS")

What it wires up (so every scenario gets the same production baseline):
  1. Structured logging + per-request id, Prometheus /metrics
  2. Uniform error envelope + stable codes
  3. License verification + expiry gate, then license-gated feature modules
  4. Versioned API: everything mounts under settings.api_prefix (default /api/v1);
     health/ready/metrics/files stay unversioned at the root.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import Settings, get_settings
from .errors import register_error_handlers
from .health import router as health_router
from .license import load_license
from .logging import RequestLoggingMiddleware, configure_logging, get_logger
from .metrics import MetricsMiddleware, metrics_response
from .modules import ModuleRegistry


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach industry-standard security response headers to every response.

    Defence-in-depth for the API tier (the reverse proxy + frontend set the same
    on HTML). Maps to OWASP Secure Headers / STQC app-security requirements:
      * HSTS                     — force HTTPS (ignored by browsers over plain HTTP)
      * X-Content-Type-Options   — no MIME sniffing
      * X-Frame-Options          — clickjacking (API is never framed)
      * Referrer-Policy          — don't leak URLs cross-origin
      * Permissions-Policy       — disable powerful browser features by default
      * Content-Security-Policy   — API returns JSON only → lock it right down
      * Cross-Origin-*           — isolate the API
    """

    _HEADERS = {
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-site",
        "X-Permitted-Cross-Domain-Policies": "none",
    }

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in self._HEADERS.items():
            response.headers.setdefault(key, value)
        # Files (crops/logos) are images, not JSON — relax CSP so they still load.
        if request.url.path.startswith("/files"):
            response.headers["Content-Security-Policy"] = "default-src 'none'; img-src 'self'"
        return response


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Coarse per-IP request cap across the whole API (abuse backstop).

    Skips health/metrics/static so probes and dashboards are never throttled.
    Single-process (in-memory window) — good enough as a first line of defence;
    front with a shared store (Redis / edge proxy) for multi-worker deployments.
    """

    def __init__(self, app, limit: int, skip_prefixes: tuple[str, ...]):
        super().__init__(app)
        self.limit = limit
        self.skip_prefixes = skip_prefixes

    async def dispatch(self, request, call_next):
        if (
            self.limit <= 0
            or request.method == "OPTIONS"
            or request.url.path.startswith(self.skip_prefixes)
        ):
            return await call_next(request)
        from .ratelimit import RateLimitError, hit

        ip = request.client.host if request.client else "unknown"
        try:
            hit(f"global:{ip}", self.limit, 60.0)
        except RateLimitError as exc:
            return JSONResponse(
                status_code=429,
                content={"error": {"code": exc.code, "message": str(exc)}},
            )
        return await call_next(request)


class LicenseEnforcementMiddleware(BaseHTTPMiddleware):
    """Block all feature access when the license is expired (the enterprise gate).

    Login, license status/update, features, branding, health and metrics stay
    reachable so an admin can sign in and upload a fresh license; everything else
    returns a LICENSE_EXPIRED envelope the frontend turns into a "License Expired"
    screen. Reads app.state.license each request → a renewal takes effect at once.
    """

    def __init__(self, app, allow_prefixes: tuple[str, ...]):
        super().__init__(app)
        self.allow_prefixes = allow_prefixes

    async def dispatch(self, request, call_next):
        if request.method == "OPTIONS":  # never block CORS preflight
            return await call_next(request)
        license = getattr(request.app.state, "license", None)
        if (
            license is not None
            and license.is_expired
            and not request.url.path.startswith(self.allow_prefixes)
        ):
            return JSONResponse(
                status_code=403,
                content={
                    "error": {
                        "code": "LICENSE_EXPIRED",
                        "message": "License expired. Please update your license to continue.",
                    }
                },
            )
        return await call_next(request)


# Placeholder secret values that MUST NOT reach production (shipped defaults +
# the ones in .env.example). Boot is refused if any survive outside dev/test.
_WEAK_SECRETS = {
    "change-me-in-prod",
    "change-me-secret",
    "change-me-to-a-long-random-string-min-32-bytes",
    "change-me-another-long-random-string",
    "",
}


def _enforce_secrets(settings: Settings, log) -> None:
    """Refuse to start outside dev/test with default or too-short crypto secrets.

    Prevents the classic "shipped with the sample JWT secret" finding — a hard
    requirement for STQC / any security audit.
    """
    if settings.env in ("dev", "test", "local"):
        if settings.jwt_secret in _WEAK_SECRETS or settings.secrets_key in _WEAK_SECRETS:
            log.warning("running with DEFAULT secrets — fine for dev, NEVER for production")
        return
    weak = []
    if settings.jwt_secret in _WEAK_SECRETS or len(settings.jwt_secret) < 32:
        weak.append("VE_JWT_SECRET (needs a strong random value, >=32 chars)")
    if settings.secrets_key in _WEAK_SECRETS or len(settings.secrets_key) < 16:
        weak.append("VE_SECRETS_KEY (needs a strong random value)")
    if weak:
        raise RuntimeError(
            f"refusing to start in env={settings.env!r}: weak/default secret(s): "
            + "; ".join(weak)
        )


def create_app(
    registry: ModuleRegistry,
    *,
    title: str = "Vizor Edge App",
    settings: Settings | None = None,
    extra_routers: Iterable[APIRouter] = (),
    lifespan=None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.env)
    log = get_logger("edge.startup")
    prefix = settings.api_prefix

    _enforce_secrets(settings, log)

    license = load_license(settings)
    log.info("license: client=%s modules=%s", license.client, sorted(license.modules))

    app = FastAPI(title=title, lifespan=lifespan)
    app.state.settings = settings
    app.state.license = license
    app.state.registry = registry

    # Endpoints reachable even under an expired license (so the app can be renewed).
    allow_prefixes = (
        "/health",
        "/ready",
        "/metrics",
        "/files",
        "/docs",
        "/redoc",
        "/openapi.json",
        f"{prefix}/auth",
        f"{prefix}/license",
        f"{prefix}/features",
        f"{prefix}/branding",
    )

    # Middleware: LAST added is OUTERMOST → request logging wraps everything.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(LicenseEnforcementMiddleware, allow_prefixes=allow_prefixes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        GlobalRateLimitMiddleware,
        limit=settings.rate_limit_global_per_minute,
        skip_prefixes=("/health", "/ready", "/metrics", "/files", "/docs", "/redoc", "/openapi.json"),
    )
    app.add_middleware(MetricsMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    register_error_handlers(app)

    # --- Unversioned root endpoints ---------------------------------------
    app.include_router(health_router)  # /health, /ready

    from .storage import files_router  # public object serving (/files/{key})

    app.include_router(files_router)

    @app.get("/metrics", include_in_schema=False)
    def metrics():
        return metrics_response()

    # --- Versioned API (everything under settings.api_prefix) -------------
    for r in extra_routers:  # always-on: auth, licensing, audit, system, ...
        app.include_router(r, prefix=prefix)

    enabled = registry.enabled(license)
    for spec in enabled:  # license-gated feature modules
        app.include_router(spec.router, prefix=f"{prefix}/modules/{spec.id}", tags=[spec.name])
    log.info("mounted modules: %s", [s.id for s in enabled])

    @app.get(f"{prefix}/features", tags=["platform"])
    def features() -> dict:
        """Frontend calls this on load to build its nav from enabled modules."""
        return {
            "client": license.client,
            "expires_at": license.expires_at.isoformat() if license.expires_at else None,
            "modules": [spec.nav for spec in enabled],
            "limits": {} if license._dev else license.limits,
            "features": {} if license._dev else license.features,
        }

    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def index() -> str:
        return _LANDING_HTML.format(title=title)

    return app


_LANDING_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>
<style>
 :root{{color-scheme:dark}} *{{box-sizing:border-box}}
 body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
  background:#000;color:#ededed;min-height:100vh;
  display:flex;align-items:center;justify-content:center;padding:24px}}
 .card{{width:100%;max-width:600px;background:#0a0a0a;border:1px solid #262626;border-radius:14px;padding:40px}}
 .badge{{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:500;letter-spacing:.02em;
  color:#a3a3a3;background:transparent;border:1px solid #262626;padding:5px 11px;border-radius:999px}}
 h1{{margin:18px 0 6px;font-size:28px;font-weight:600;letter-spacing:-.02em;color:#fff}}
 p.sub{{margin:0 0 28px;color:#8f8f8f;font-size:14px}}
 .grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}
 a.tile{{display:block;text-decoration:none;color:#ededed;background:transparent;border:1px solid #262626;
  border-radius:10px;padding:15px 17px;transition:.15s}}
 a.tile:hover{{border-color:#525252;background:#111}}
 a.tile b{{display:block;font-size:14px;margin-bottom:2px;font-weight:500}} a.tile span{{font-size:13px;color:#8f8f8f}}
 .dot{{width:7px;height:7px;border-radius:50%;background:#3ecf8e;box-shadow:0 0 0 3px rgba(62,207,142,.15)}}
 footer{{margin-top:26px;font-size:12px;color:#666}}
</style></head><body>
 <div class="card">
  <span class="badge"><span class="dot"></span>API online</span>
  <h1>{title}</h1>
  <p class="sub">Backend API is running. This is the API host — the application UI runs separately.</p>
  <div class="grid">
   <a class="tile" href="/docs"><b>API Docs &rarr;</b><span>Interactive Swagger UI</span></a>
   <a class="tile" href="/redoc"><b>ReDoc &rarr;</b><span>Reference documentation</span></a>
   <a class="tile" href="/health"><b>Health &rarr;</b><span>Liveness probe</span></a>
   <a class="tile" href="/metrics"><b>Metrics &rarr;</b><span>Prometheus</span></a>
  </div>
  <footer>Powered by the Vizor edge platform &middot; app UI at http://localhost:3000</footer>
 </div>
</body></html>"""

