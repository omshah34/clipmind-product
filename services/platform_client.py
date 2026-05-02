import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass

import httpx

from core.redis import get_redis_client

logger = logging.getLogger(__name__)

_RATE_STATE_TTL_SECONDS = 3600
_MAX_429_RETRIES = 2

@dataclass
class RateLimitState:
    reset_at: float = 0.0
    remaining: int = 999

_rate_states: dict[str, RateLimitState] = {}


def _state_key(platform: str) -> str:
    return f"clipmind:platform-rate:{platform}"


def _load_shared_state(platform: str) -> RateLimitState | None:
    try:
        client = get_redis_client()
        raw = client.get(_state_key(platform))
        if not raw:
            return None
        payload = json.loads(raw)
        return RateLimitState(
            reset_at=float(payload.get("reset_at", 0.0)),
            remaining=int(payload.get("remaining", 999)),
        )
    except Exception:
        return None


def _store_shared_state(platform: str, state: RateLimitState) -> None:
    try:
        client = get_redis_client()
        client.set(_state_key(platform), json.dumps(asdict(state)), ex=_RATE_STATE_TTL_SECONDS)
    except Exception:
        return

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
    state = _rate_states.get(platform) or _load_shared_state(platform) or RateLimitState()
    _rate_states[platform] = state

    for attempt in range(_MAX_429_RETRIES + 1):
        wait = state.reset_at - time.time()
        if state.remaining <= 1 and wait > 0:
            logger.warning(f"[{platform}] Rate limit active — sleeping {wait:.1f}s")
            await asyncio.sleep(wait + 0.5)

        async with httpx.AsyncClient(timeout=30.0) as client:
            request_func = getattr(client, method.lower())
            resp = await request_func(url, **kwargs)

        remaining = resp.headers.get("X-RateLimit-Remaining") or resp.headers.get("x-rate-limit-remaining")
        reset = resp.headers.get("X-RateLimit-Reset") or resp.headers.get("x-rate-limit-reset")

        if remaining is not None:
            try:
                state.remaining = int(remaining)
            except ValueError:
                pass

        if reset is not None:
            try:
                reset_val = float(reset)
                state.reset_at = reset_val if reset_val > 1_000_000 else time.time() + reset_val
            except ValueError:
                pass

        _store_shared_state(platform, state)

        if resp.status_code != 429:
            return resp

        if attempt >= _MAX_429_RETRIES:
            return resp

        retry_after_raw = resp.headers.get("Retry-After", "60")
        try:
            retry_after = float(retry_after_raw)
        except ValueError:
            retry_after = 60.0
        logger.warning(f"[{platform}] 429 received — waiting {retry_after}s before retry {attempt + 1}/{_MAX_429_RETRIES}")
        await asyncio.sleep(retry_after)

    return resp
