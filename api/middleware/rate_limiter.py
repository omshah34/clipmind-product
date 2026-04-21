"""File: api/middleware/rate_limiter.py
Purpose: Production-grade Redis-backed Sliding Window Rate Limiter.
         Prevents API abuse and ensures fair resource distribution.
"""

import time
import logging
import asyncio
from typing import Callable, Awaitable
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings
from workers.celery_app import celery_app # Reusing redis connection from celery app if possible, or separate

logger = logging.getLogger(__name__)

# LUA Script for Atomic Sliding Window
# KEYS[1]: the rate limit key (e.g., ratelimit:user_id:endpoint)
# ARGV[1]: current timestamp (milliseconds)
# ARGV[2]: window size (milliseconds)
# ARGV[3]: limit
# ARGV[4]: TTL (seconds)
LUA_SLIDING_WINDOW = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

-- Remove old entries
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)

-- Count current entries
local current_count = redis.call('ZCARD', key)

if current_count < limit then
    -- Add current request
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, ttl)
    return {current_count + 1, 1} -- {count, allowed}
else
    return {current_count, 0} -- {count, denied}
end
"""

class SlidingWindowRateLimiter(BaseHTTPMiddleware):
    def __init__(
        self, 
        app, 
        limit: int = 100, 
        window_seconds: int = 60,
        exclude_paths: list[str] = None
    ):
        super().__init__(app)
        self.limit = limit
        self.window_ms = window_seconds * 1000
        self.ttl = window_seconds + 10
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/openapi.json"]
        
        # Initialize Redis client lazily
        self.redis = None
        self._lua_sha = None

    async def get_redis(self):
        if not self.redis:
            import redis.asyncio as redis
            self.redis = redis.from_url(settings.redis_url)
            # Register LUA script
            self._lua_sha = await self.redis.script_load(LUA_SLIDING_WINDOW)
        return self.redis

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # 1. Skip excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # 2. Identify user (fallback to IP for unauthenticated)
        # Note: In production, we'd pull this from the dependency but middleware 
        # runs before dependencies. We extract from state or headers.
        user_id = "anonymous"
        auth_header = request.headers.get("Authorization")
        if auth_header:
            # Simple hash of token as user identifier if we can't decode it yet
            import hashlib
            user_id = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
        else:
            user_id = request.client.host if request.client else "unknown"

        # 3. Apply Limit
        key = f"ratelimit:{user_id}:{request.url.path}"
        now_ms = int(time.time() * 1000)

        try:
            r = await self.get_redis()
            # Execute atomic LUA script
            # evalsha(sha, numkeys, *keys_and_args)
            result = await r.evalsha(self._lua_sha, 1, key, now_ms, self.window_ms, self.limit, self.ttl)
            count, allowed = result

            if not allowed:
                logger.warning(f"Rate limit exceeded for user {user_id} on {request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "detail": "Too many requests. Please try again later.",
                        "limit": self.limit,
                        "window_seconds": self.window_ms // 1000
                    }
                )

            # 4. Success — proceed
            response = await call_next(request)
            
            # Add headers for transparency
            response.headers["X-RateLimit-Limit"] = str(self.limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, self.limit - count))
            return response

        except Exception as exc:
            # FAIL-OPEN Strategy: If Redis is down, allow the request but log the error.
            # Production visibility is key, but availability is paramount for a SaaS start.
            logger.error(f"Rate limiter failure (Fail-Open): {exc}")
            return await call_next(request)
