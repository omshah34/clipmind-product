import asyncio
import time
import httpx
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RateLimitState:
    reset_at: float = 0.0
    remaining: int = 999

_rate_states: dict[str, RateLimitState] = {}

async def platform_request(
    platform: str,
    method: str,
    url: str,
    **kwargs,
) -> httpx.Response:
    """
    Gap 282: Rate limit aware platform request.
    Respects X-RateLimit-Remaining and X-RateLimit-Reset headers.
    """
    state = _rate_states.setdefault(platform, RateLimitState())

    # Respect reset window before sending
    wait = state.reset_at - time.time()
    if state.remaining <= 1 and wait > 0:
        logger.warning(f"[{platform}] Rate limit active — sleeping {wait:.1f}s")
        await asyncio.sleep(wait + 0.5)  # +0.5s buffer

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get the method (get, post, etc.) from the client
        request_func = getattr(client, method.lower())
        resp = await request_func(url, **kwargs)

    # Parse standard rate limit headers
    remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("x-rate-limit-remaining")
    reset = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-rate-limit-reset")

    if remaining is not None:
        try:
            state.remaining = int(remaining)
        except ValueError:
            pass

    if reset is not None:
        try:
            # Reset can be epoch seconds or delta seconds — handle both
            reset_val = float(reset)
            state.reset_at = reset_val if reset_val > 1_000_000 else time.time() + reset_val
        except ValueError:
            pass

    # Handle 429 explicitly — wait for Retry-After
    if resp.status_code == 429:
        retry_after = float(resp.headers.get("Retry-After", 60))
        logger.warning(f"[{platform}] 429 received — waiting {retry_after}s")
        await asyncio.sleep(retry_after)
        return await platform_request(platform, method, url, **kwargs)  # one retry

    return resp
