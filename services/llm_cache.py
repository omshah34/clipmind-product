"""File: services/llm_cache.py
Purpose: Redis-backed exact-match cache for deterministic LLM calls.
         Reduces latency and cost for repeated operations.
"""

import hashlib
import json
import logging
from typing import Any, Optional

import redis
from core.config import settings

logger = logging.getLogger(__name__)

class LLMCache:
    def __init__(self):
        try:
            self.redis = redis.from_url(settings.redis_url)
            self.enabled = True
        except Exception as e:
            logger.warning("Redis not available for LLM Cache: %s", e)
            self.enabled = False

    def _generate_key(self, prompt: str, model: str, **kwargs) -> str:
        """Create a unique SHA-256 hash for the prompt and parameters."""
        payload = {
            "prompt": prompt,
            "model": model,
            "params": sorted(kwargs.items())
        }
        payload_str = json.dumps(payload, sort_keys=True)
        return f"llm_cache:{hashlib.sha256(payload_str.encode()).hexdigest()}"

    def get(self, prompt: str, model: str, **kwargs) -> Optional[dict]:
        """Retrieve a cached response if it exists."""
        if not self.enabled:
            return None
            
        key = self._generate_key(prompt, model, **kwargs)
        try:
            cached = self.redis.get(key)
            if cached:
                logger.info("LLM Cache HIT for prompt hash %s", key.split(":")[1][:8])
                return json.loads(cached)
        except Exception as e:
            logger.error("Error reading from LLM cache: %s", e)
        return None

    def set(self, prompt: str, model: str, response: Any, **kwargs):
        """Store a response in the cache with a 24-hour TTL."""
        if not self.enabled:
            return
            
        key = self._generate_key(prompt, model, **kwargs)
        try:
            # Store as JSON
            self.redis.setex(
                key, 
                86400, # 24 hours
                json.dumps(response)
            )
        except Exception as e:
            logger.error("Error writing to LLM cache: %s", e)

# Singleton instance
llm_cache = LLMCache()
