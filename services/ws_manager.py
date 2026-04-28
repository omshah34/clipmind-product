"""File: services/ws_manager.py
Purpose: WebSocket connection manager for real-time pipeline progress.
         Tracks active connections per job and broadcasts stage events
         to all watchers. Used by pipeline.py to push live updates.
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from typing import Any

import redis
import redis.asyncio as async_redis

from core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process event bus (sync → async bridge)
# ---------------------------------------------------------------------------
_event_buffers: dict[str, list[dict]] = defaultdict(list)
_MAX_BUFFER = 200
_REDIS_EVENT_TTL_SECONDS = 3600

class WSManager:
    def __init__(self):
        self._sync_redis: redis.Redis | None = None
        self._async_redis: async_redis.Redis | None = None

    async def init_redis(self, app=None):
        """Gap 208: Initialize shared Redis clients (called at startup)."""
        try:
            # Sync client for publishing (backward compatibility with Celery)
            self._sync_redis = redis.Redis.from_url(
                settings.redis_url,
                socket_timeout=min(settings.redis_socket_timeout, 3),
                socket_connect_timeout=min(settings.redis_socket_connect_timeout, 3),
                decode_responses=True,
            )
            
            # Async client for FastAPI WebSocket loops
            self._async_redis = async_redis.Redis.from_url(
                settings.redis_url,
                socket_timeout=min(settings.redis_socket_timeout, 3),
                socket_connect_timeout=min(settings.redis_socket_connect_timeout, 3),
                decode_responses=True,
            )
            
            # Verify connectivity
            self._sync_redis.ping()
            await self._async_redis.ping()
            
            logger.info("[ws] Redis clients initialized (sync + async)")
        except Exception as exc:
            logger.error("[ws] Failed to initialize Redis clients: %s", exc)
            self._sync_redis = None
            self._async_redis = None

    async def close_redis(self, app=None):
        """Gap 208: Close shared Redis clients (called at shutdown)."""
        if self._async_redis:
            await self._async_redis.aclose()
        if self._sync_redis:
            self._sync_redis.close()
        logger.info("[ws] Redis clients closed")

    def _redis_key(self, job_id: str) -> str:
        return f"clipmind:ws-events:{job_id}"

    def publish_event(self, job_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Publish a pipeline event (called from sync worker code)."""
        event = {
            "type": event_type,
            "job_id": job_id,
            "data": data or {},
            "timestamp": time.time(),
        }
        
        # Local memory buffer (legacy fallback/redundancy)
        buf = _event_buffers[job_id]
        buf.append(event)
        if len(buf) > _MAX_BUFFER:
            _event_buffers[job_id] = buf[-_MAX_BUFFER:]

        # Shared Sync Redis
        client = self._sync_redis or self._get_fallback_sync_client()
        if client:
            try:
                payload = json.dumps(event, separators=(",", ":"))
                key = self._redis_key(job_id)
                pipe = client.pipeline(transaction=False)
                pipe.rpush(key, payload)
                pipe.ltrim(key, -_MAX_BUFFER, -1)
                pipe.expire(key, _REDIS_EVENT_TTL_SECONDS)
                pipe.execute()
            except Exception:
                logger.debug("[ws] Redis publish failed for job=%s", job_id)

    def _get_fallback_sync_client(self) -> redis.Redis | None:
        """Fallback for environments where lifespan wasn't called (e.g. CLI/tests)."""
        try:
            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    async def drain_events(self, job_id: str, after: float = 0.0) -> list[dict]:
        """Return all events for *job_id* with timestamp > *after* (Async)."""
        if self._async_redis:
            try:
                raw_events = await self._async_redis.lrange(self._redis_key(job_id), 0, -1)
                events = [json.loads(item) for item in raw_events]
                return [event for event in events if event.get("timestamp", 0.0) > after]
            except Exception:
                logger.debug("[ws] Redis async drain failed for job=%s", job_id)

        # Fallback to local memory buffer
        return [e for e in _event_buffers.get(job_id, []) if e["timestamp"] > after]

    async def clear_events(self, job_id: str) -> None:
        """Remove all buffered events for a job (Async)."""
        _event_buffers.pop(job_id, None)
        if self._async_redis:
            try:
                await self._async_redis.delete(self._redis_key(job_id))
            except Exception:
                logger.debug("[ws] Redis async clear failed for job=%s", job_id)

# Singleton instance
ws_manager = WSManager()

# Legacy function exports to maintain backward compatibility with pipeline.py
def publish_event(job_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
    ws_manager.publish_event(job_id, event_type, data)

async def drain_events(job_id: str, after: float = 0.0) -> list[dict]:
    return await ws_manager.drain_events(job_id, after)

async def clear_events(job_id: str) -> None:
    await ws_manager.clear_events(job_id)

# Convenience helpers
def emit_stage(job_id: str, stage: str, progress: int = 0, **extra: Any) -> None:
    publish_event(job_id, "stage_change", {"stage": stage, "progress": progress, **extra})

def emit_progress(job_id: str, stage: str, progress: int, **extra: Any) -> None:
    publish_event(job_id, "progress", {"stage": stage, "progress": progress, **extra})

def emit_clip_scored(job_id: str, clip_index: int, scores: dict, reason: str = "") -> None:
    publish_event(job_id, "clip_scored", {"clip_index": clip_index, "scores": scores, "reason": reason})

def emit_clip_ready(job_id: str, clip_index: int, duration: float, final_score: float) -> None:
    publish_event(job_id, "clip_ready", {"clip_index": clip_index, "duration": duration, "final_score": final_score})

def emit_completed(job_id: str, total_clips: int, best_score: float, processing_time: float) -> None:
    publish_event(job_id, "completed", {"total_clips": total_clips, "best_score": best_score, "processing_time_seconds": round(processing_time, 1)})

def emit_error(job_id: str, stage: str, message: str) -> None:
    publish_event(job_id, "error", {"stage": stage, "message": message})
