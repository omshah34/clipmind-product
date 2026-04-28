"""File: api/main.py
Purpose: FastAPI application entry point. Registers all routes and middleware,
         exposes the backend API server, and handles CORS configuration.
"""

from __future__ import annotations

from core.logging_config import setup_logging
setup_logging()

import logging
import os
import time
import traceback

import redis
from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from starlette.middleware.gzip import GZipMiddleware
from db.connection import DatabaseTimeoutException
from services.ws_manager import ws_manager
from services.storage import storage_service

# Gap 21: Prevent Log Destruction - Setup logging handled in setup_logging()
# but we can add a marker here if needed.

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("ClipMind API starting up...")
    
    # Gap 208: Initialize shared Redis clients
    await ws_manager.init_redis(app)
    
    yield
    # Shutdown
    logger.info("ClipMind API shutting down...")
    
    # Gap 208: Close shared Redis clients
    await ws_manager.close_redis(app)
    
    # Gap 104: Close Redis connection on rate limiter
    for middleware in app.user_middleware:
        if hasattr(middleware, "options") and "cls" in middleware.options:
            if middleware.options["cls"] == SlidingWindowRateLimiter:
                if hasattr(app.state, "rate_limiter"):
                    await app.state.rate_limiter.close()
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
except ModuleNotFoundError:  # optional dependency in lean test environments
    sentry_sdk = None

    class FastApiIntegration:  # type: ignore[too-many-ancestors]
        def __init__(self, *args, **kwargs):
            pass

from api.middleware.rate_limiter import SlidingWindowRateLimiter
from api.middleware.request_context import RequestContextMiddleware
from api.dependencies import get_current_user, AuthenticatedUser
from db.feature_flags import feature_flag_enabled

from api.routes.jobs import router as jobs_router
from api.routes.upload import router as upload_router
from api.routes.brand_kits import router as brand_kits_router
from api.routes.clip_studio import router as clip_studio_router
from api.routes.campaigns import router as campaigns_router
from api.routes.api_keys import router as api_keys_router
from api.routes.webhooks import router as webhooks_router
from api.routes.integrations import integrations_router
from api.routes.performance import performance_router
from api.routes.preview_studio import router as preview_studio_router
from api.routes.content_dna import router as content_dna_router
from api.routes.clip_sequences import router as clip_sequences_router
from api.routes.social_publish import router as social_publish_router
from api.routes.publish import router as publish_router
from api.routes.workspaces import router as workspaces_router
from api.routes.billing import router as billing_router
from api.routes.preferences import router as preferences_router
from api.routes.websockets import router as websockets_router
from api.routes.autopilot import router as autopilot_router
from api.routes.performance_alerts import router as performance_alerts_router
from api.routes.oauth import router as oauth_router
from api.routes.hooks import router as hooks_router
from api.routes.exports import exports_router
from core.config import settings

logger = logging.getLogger(__name__)

# Sentry Initialization
if os.getenv("SENTRY_DSN"):
    if sentry_sdk is not None:
        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
            profiles_sample_rate=0.1,
            environment=os.getenv("ENVIRONMENT", "development"),
        )

app = FastAPI(title="ClipMind API", version="0.1.0", lifespan=lifespan)

# TODO: Fetch these dynamically before launch from:
# Stripe: https://stripe.com/files/ips/ips_webhooks.json
# Google: https://www.gstatic.com/ipranges/goog.json
PLATFORM_WEBHOOK_CIDRS = [
    # Stripe (Sample subset for dev)
    "3.18.12.63/32", "3.130.192.231/32", "13.235.14.237/32", "13.235.122.149/32",
    "18.211.135.69/32", "35.154.171.200/32", "52.15.183.38/32", "54.88.130.119/32",
    "54.88.130.237/32", "54.187.174.169/32", "54.187.205.235/32", "54.187.216.72/32",
]

# Add Rate Limiter Middleware
app.add_middleware(
    SlidingWindowRateLimiter,
    limit=100,           # 100 requests
    window_seconds=60,   # per minute
    allowlist_ips=PLATFORM_WEBHOOK_CIDRS,
    allowlist_limit=500,  # Elevated limit for webhooks
)

app.add_middleware(RequestContextMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def log_request_summary(request: Request, call_next):
    started_at = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "[http] %s %s -> %s (%sms, content-length=%s)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
        request.headers.get("content-length", "0"),
    )
    return response

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Inject security-hardening headers into every response."""
    response = await call_next(request)
    # HSTS: Force HTTPS (production only)
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    # Anti-Clickjacking
    response.headers["X-Frame-Options"] = "DENY"
    # Mime-Sniffing Prevention
    response.headers["X-Content-Type-Options"] = "nosniff"
    # XSS Protection for older browsers
    response.headers["X-XSS-Protection"] = "1; mode=block"
    # Basic Content Security Policy
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:* *.clipmind.com"
    )
    # Gap 81: Referrer-Policy — prevent leaking internal dashboard URLs to external sites
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Permissions Policy — disable access to camera/mic/location by default
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Vary"] = "Origin"
    
    return response

DEV_ORIGINS = [
    f"http://localhost:{port}" for port in range(3000, 3011)
] + [
    f"http://127.0.0.1:{port}" for port in range(3000, 3011)
]

ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "http://localhost:3000"),
    *DEV_ORIGINS,
    "https://app.clipmind.com",
    "https://clipmind.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    # Gap 51: Restrict to an explicit method whitelist instead of wildcard
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept", "Origin"],
)

# Gap 79: html=False disables directory listing on the static file server
app.mount("/storage", StaticFiles(directory=settings.local_storage_dir, html=False), name="storage")

if feature_flag_enabled("dev_auth_bypass", default=os.getenv("ENVIRONMENT", "").lower() in {"", "development", "local", "test"}):
    async def _dev_user_override() -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id=settings.dev_mock_user_id,
            email="local@clipmind.com",
            role="owner",
        )

    app.dependency_overrides[get_current_user] = _dev_user_override

# ---------------------------------------------------------------------------
# Global exception handler — ensures CORS headers are attached even on 500s
# ---------------------------------------------------------------------------
@app.exception_handler(DatabaseTimeoutException)
async def db_timeout_handler(request: Request, exc: DatabaseTimeoutException):
    """Gap 207: Handle DB pool exhaustion gracefully."""
    logger.warning("Database connection pool exhausted: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"message": "Service temporarily unavailable due to high load. Please try again in a few seconds."},
        headers={"Retry-After": "5"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    # Gap 64: Attach user context to Sentry if available
    if sentry_sdk and hasattr(request.state, "user_id") and request.state.user_id:
        sentry_sdk.set_user({"id": str(request.state.user_id)})
    if os.getenv("ENVIRONMENT") == "development":
        return JSONResponse(status_code=500, content={"message": str(exc)})
    return JSONResponse(status_code=500, content={"message": "Internal Server Error"})


# Protected routes
auth_deps = [Depends(get_current_user)]
app.include_router(upload_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(jobs_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(brand_kits_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(clip_studio_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(campaigns_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(api_keys_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(integrations_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(performance_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(preview_studio_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(content_dna_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(clip_sequences_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(social_publish_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(publish_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(workspaces_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(billing_router, prefix="/api/v1/billing", dependencies=auth_deps)
app.include_router(preferences_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(autopilot_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(performance_alerts_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(hooks_router, prefix="/api/v1", dependencies=auth_deps)
app.include_router(exports_router, prefix="/api/v1", dependencies=auth_deps)

# Unprotected routes (Webhooks handle their own signature verification, Websockets have tokens in URL/headers)
app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(websockets_router, prefix="/api/v1")
app.include_router(oauth_router, prefix="/api/v1")


@app.get("/health")
async def healthcheck() -> dict:
    """Deep health check: verifies core infrastructure connectivity.
    
    Gap 69: Now also probes upstream AI API connectivity.
    """
    health = {
        "status": "ok",
        "api": "healthy",
        "dependencies": {},
        "capabilities": {
            "direct_upload": storage_service.is_cloud_storage_enabled(),
            "multipart_upload": storage_service.is_cloud_storage_enabled(),
            "cloud_storage": storage_service.is_cloud_storage_enabled(),
        },
    }
    status_code = 200

    # 1. Check Database
    try:
        from db.connection import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["dependencies"]["postgres"] = "healthy"
    except Exception as e:
        logger.error(f"Health check: Postgres failure: {e}")
        health["dependencies"]["postgres"] = "unhealthy"
        health["status"] = "degraded"
        status_code = 503

    # 2. Check Redis & Workers (Gap 35, 68)
    try:
        from workers.celery_app import celery_app

        # Use redis-py's client API for Redis commands. Celery/Kombu exposes
        # pooled transport connections here, not a redis.Redis instance.
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_timeout=settings.redis_socket_timeout,
            socket_connect_timeout=settings.redis_socket_connect_timeout,
            decode_responses=True,
        )
        try:
            client.ping()

            # Gap 35: Redis Memory Health
            redis_info = client.info("memory")
            used_mb = round(redis_info.get("used_memory", 0) / (1024 * 1024), 2)
            peak_mb = round(redis_info.get("used_memory_peak", 0) / (1024 * 1024), 2)
            health["dependencies"]["redis"] = {
                "status": "healthy",
                "used_memory_mb": used_mb,
                "peak_memory_mb": peak_mb,
                "fragmentation_ratio": redis_info.get("mem_fragmentation_ratio")
            }
        finally:
            client.close()

        # Gap 68: Check Worker Load & Concurrency (only in non-dev or if forced)
        if os.getenv("ENVIRONMENT") != "development":
            inspector = celery_app.control.inspect()
            stats = inspector.stats() or {}
            active = inspector.active() or {}
            
            workers_info = []
            for name, stat in stats.items():
                workers_info.append({
                    "name": name,
                    "concurrency": stat.get("pool", {}).get("max-concurrency"),
                    "active_tasks": len(active.get(name, [])),
                    "is_running": True
                })
            
            if workers_info:
                health["dependencies"]["celery_workers"] = {
                    "status": "healthy",
                    "count": len(workers_info),
                    "details": workers_info
                }
            else:
                health["dependencies"]["celery_workers"] = "unhealthy (none online)"
                health["status"] = "degraded"
                status_code = 503
    except Exception as e:
        logger.error(f"Health check: Redis/Celery failure: {e}")
        health["dependencies"]["redis"] = "unhealthy"
        health["status"] = "degraded"
        status_code = 503

    # 3. Gap 69: Check upstream AI API reachability (lightweight probes, 5s timeout)
    import httpx
    _ai_checks = {}

    # OpenAI probe
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
            _ai_checks["openai"] = "reachable" if r.status_code < 500 else f"error ({r.status_code})"
        except Exception as e:
            _ai_checks["openai"] = f"unreachable ({type(e).__name__})"
            health["status"] = "degraded"
    else:
        _ai_checks["openai"] = "not_configured"

    # Groq probe
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"},
                )
            _ai_checks["groq"] = "reachable" if r.status_code < 500 else f"error ({r.status_code})"
        except Exception as e:
            _ai_checks["groq"] = f"unreachable ({type(e).__name__})"
    else:
        _ai_checks["groq"] = "not_configured"

    health["dependencies"]["ai_apis"] = _ai_checks
    from datetime import datetime, timezone

    health["timestamp"] = datetime.now(timezone.utc).isoformat()
    return JSONResponse(status_code=status_code, content=health)
