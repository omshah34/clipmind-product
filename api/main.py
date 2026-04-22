"""File: api/main.py
Purpose: FastAPI application entry point. Registers all routes and middleware,
         exposes the backend API server, and handles CORS configuration.
"""

from __future__ import annotations

from core.logging_config import setup_logging
setup_logging()

import logging
import os
import traceback

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
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

app = FastAPI(title="ClipMind API", version="0.1.0")

# Add Rate Limiter Middleware
app.add_middleware(
    SlidingWindowRateLimiter,
    limit=100,           # 100 requests
    window_seconds=60    # per minute
)
app.add_middleware(RequestContextMiddleware)

ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "http://localhost:3000"),
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
    "https://app.clipmind.com",
    "https://clipmind.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/storage", StaticFiles(directory=settings.local_storage_dir), name="storage")

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
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
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
    """Deep health check: verifies core infrastructure connectivity."""
    health = {
        "status": "ok",
        "api": "healthy",
        "dependencies": {}
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

    # 2. Check Redis & Workers
    try:
        from workers.celery_app import celery_app
        # Ping Redis via celery's connection pool
        with celery_app.connection_or_acquire() as conn:
            conn.default_channel.connection.client.ping()
        health["dependencies"]["redis"] = "healthy"
        
        # Ping Workers (only in production)
        if os.getenv("ENVIRONMENT") != "development":
            inspector = celery_app.control.inspect()
            pings = inspector.ping()
            if pings:
                health["dependencies"]["celery_workers"] = f"healthy ({len(pings)} online)"
            else:
                health["dependencies"]["celery_workers"] = "unhealthy (none online)"
                health["status"] = "degraded"
                status_code = 503
    except Exception as e:
        logger.error(f"Health check: Redis/Celery failure: {e}")
        health["dependencies"]["redis"] = "unhealthy"
        health["status"] = "degraded"
        status_code = 503

    return JSONResponse(status_code=status_code, content=health)
