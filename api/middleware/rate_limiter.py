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
from redis.exceptions import NoScriptError
from starlette.middleware.base import BaseHTTPMiddleware

from core.config import settings

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
        exclude_paths: list[str] = None,
        allowlist_ips: list[str] = None,
        allowlist_limit: int = 500,
    ):
        super().__init__(app)
        self.limit = limit
        self.window_ms = window_seconds * 1000
        self.ttl = window_seconds + 10
        self.exclude_paths = exclude_paths or ["/health", "/docs", "/openapi.json"]
        self.allowlist_ips = allowlist_ips or []
        self.allowlist_limit = allowlist_limit
        
        # Initialize Redis client lazily
        self.redis = None
        self._lua_sha = None
        self._lock = asyncio.Lock()

    async def get_redis(self):
        if self.redis and self._lua_sha:
            return self.redis

        async with self._lock:
            if self.redis and self._lua_sha:
                return self.redis

            import redis.asyncio as redis

            client = self.redis or redis.from_url(settings.redis_url)
            try:
                sha = await client.script_load(LUA_SLIDING_WINDOW)
                if not sha:
                    raise ValueError("Failed to load rate limiter LUA script")
            except Exception:
                try:
                    await client.aclose()
                except Exception:
                    logger.debug("Failed to close rate limiter Redis client after script load error.", exc_info=True)
                self.redis = None
                self._lua_sha = None
                raise

            self.redis = client
            self._lua_sha = sha
        return self.redis

    async def close(self):
        """Close Redis connection on shutdown."""
        if self.redis:
            await self.redis.aclose()
            self.redis = None
            logger.info("Rate limiter Redis connection closed.")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not hasattr(request.app.state, "rate_limiter"):
            request.app.state.rate_limiter = self

        # 1. Skip excluded paths
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # 2. Identify user (fallback to IP for unauthenticated)
        # Note: In production, we'd pull this from the dependency but middleware 
        # runs before dependencies. We extract from state or headers.
        user_id = "anonymous"
        auth_header = request.headers.get("Authorization")
        client_ip = request.client.host if request.client else "unknown"
        
        if auth_header:
            # Simple hash of token as user identifier if we can't decode it yet
            import hashlib
            user_id = hashlib.sha256(auth_header.encode()).hexdigest()[:16]
        else:
            import hashlib
            user_id = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

        # 3. Check Allowlist for elevated limits (Gap 23: Webhook DoS Protection)
        current_limit = self.limit
        if client_ip != "unknown" and self.allowlist_ips:
            import ipaddress
            try:
                ip_obj = ipaddress.ip_address(client_ip)
                for cidr in self.allowlist_ips:
                    if ip_obj in ipaddress.ip_network(cidr):
                        current_limit = self.allowlist_limit
                        break
            except ValueError:
                pass

        # 4. Apply Limit
        key = f"ratelimit:{user_id}:{request.url.path}"
        now_ms = int(time.time() * 1000)

        try:
            r = await self.get_redis()
            if not self._lua_sha:
                raise ValueError("Rate limiter LUA script SHA is missing")
                
            # Execute atomic LUA script
            try:
                result = await r.evalsha(self._lua_sha, 1, key, now_ms, self.window_ms, current_limit, self.ttl)
            except NoScriptError:
                logger.warning("Rate limiter LUA script evicted from Redis, reloading.")
                self._lua_sha = None
                r = await self.get_redis()
                if not self._lua_sha:
                    raise ValueError("Rate limiter LUA script SHA is missing after reload")
                result = await r.evalsha(self._lua_sha, 1, key, now_ms, self.window_ms, current_limit, self.ttl)
            if result is None:
                raise ValueError("Rate limiter LUA script returned None")
            count, allowed = result

        except Exception as exc:
            # FAIL-OPEN Strategy: If Redis is down, allow the request but log the error.
            # Production visibility is key, but availability is paramount for a SaaS start.
            logger.error(f"Rate limiter failure (Fail-Open): {exc}")
            return await call_next(request)

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
