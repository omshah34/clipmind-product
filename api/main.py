"""File: api/main.py
Purpose: FastAPI application entry point. Registers all routes and middleware,
         exposes the backend API server, and handles CORS configuration.
"""

from __future__ import annotations
import asyncio

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
from core.config import get_runtime_config_warnings, settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("ClipMind API starting up...")
    for warning in get_runtime_config_warnings():
        logger.warning("Config warning: %s", warning)
    
    # Gap 370: Set global exception handler for truly unhandled cases
    asyncio.get_event_loop().set_exception_handler(_handle_task_exception)
    
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
from api.v1.router import v1_router

logger = logging.getLogger(__name__)

# Gap 370: Global registry for background tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()

def safe_background_task(coro):
    """
    Wrap a coroutine so exceptions are always logged/reported.
    Never swallow silently.
    """
    async def _wrapped():
        try:
            await coro
        except asyncio.CancelledError:
            raise  # Normal — don't log
        except Exception as e:
            logger.error(f"Background task failed: {e}", exc_info=True)
            if sentry_sdk:
                sentry_sdk.capture_exception(e)

    task = asyncio.create_task(_wrapped())
    # Keep strong reference — prevents GC from killing the task
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task

def _handle_task_exception(loop, context):
    """Gap 370: Global asyncio exception handler."""
    exc = context.get("exception")
    msg = context.get("message")
    logger.error(f"Unhandled asyncio exception: {msg}", exc_info=exc)
    if exc and sentry_sdk:
        sentry_sdk.capture_exception(exc)

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

# Webhook CIDRs for rate limiting bypass
PLATFORM_WEBHOOK_CIDRS = [
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
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:* *.clipmind.com"
    )
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Vary"] = "Origin"
    
    return response

ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "http://localhost:3000"),
    "http://localhost:3000",
    "https://app.clipmind.com",
    "https://clipmind.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID", "Accept", "Origin"],
)

# Static files
app.mount("/storage", StaticFiles(directory=settings.local_storage_dir, html=False), name="storage")

# Include API v1
app.include_router(v1_router, prefix="/api/v1")

# Global exception handlers
@app.exception_handler(DatabaseTimeoutException)
async def db_timeout_handler(request: Request, exc: DatabaseTimeoutException):
    logger.warning("Database connection pool exhausted: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"message": "Service temporarily unavailable due to high load. Please try again in a few seconds."},
        headers={"Retry-After": "5"}
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    if sentry_sdk and hasattr(request.state, "user_id") and request.state.user_id:
        sentry_sdk.set_user({"id": str(request.state.user_id)})
    if os.getenv("ENVIRONMENT") == "development":
        return JSONResponse(status_code=500, content={"message": str(exc)})
    return JSONResponse(status_code=500, content={"message": "Internal Server Error"})

@app.get("/health")
async def healthcheck() -> dict:
    health = {
        "status": "ok",
        "api": "healthy",
        "dependencies": {},
    }
    status_code = 200
    try:
        from db.connection import fast_engine
        from sqlalchemy import text
        with fast_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health["dependencies"]["postgres"] = "healthy"
    except Exception:
        health["dependencies"]["postgres"] = "unhealthy"
        health["status"] = "degraded"
        status_code = 503
    return JSONResponse(status_code=status_code, content=health)
