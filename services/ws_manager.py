"""File: services/ws_manager.py
Purpose: WebSocket connection manager for real-time pipeline progress.
         Tracks active connections per job and broadcasts stage events
         to all watchers. Used by pipeline.py to push live updates.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-process event bus (sync → async bridge)
# ---------------------------------------------------------------------------
# Pipeline workers run in a synchronous Celery context, so they can't
# directly call async WebSocket methods.  Instead, they push events into
# a simple in-memory list that the WebSocket endpoint polls.
# For multi-process deployments, swap this for Redis Pub/Sub.

_event_buffers: dict[str, list[dict]] = defaultdict(list)
_MAX_BUFFER = 200  # keep last N events per job


def publish_event(job_id: str, event_type: str, data: dict[str, Any] | None = None) -> None:
    """Publish a pipeline event (called from sync worker code).

    Args:
        job_id: The job this event belongs to.
        event_type: One of: stage_change, progress, clip_scored,
                    clip_ready, completed, error.
        data: Arbitrary JSON-serialisable payload.
    """
    event = {
        "type": event_type,
        "job_id": job_id,
        "data": data or {},
        "timestamp": time.time(),
    }
    buf = _event_buffers[job_id]
    buf.append(event)
    # Trim old events
    if len(buf) > _MAX_BUFFER:
        _event_buffers[job_id] = buf[-_MAX_BUFFER:]

    logger.debug("[ws] Event published: job=%s type=%s", job_id, event_type)


def drain_events(job_id: str, after: float = 0.0) -> list[dict]:
    """Return all events for *job_id* with timestamp > *after*.

    Non-destructive — events stay in the buffer so late joiners can
    catch up on recent history.
    """
    return [e for e in _event_buffers.get(job_id, []) if e["timestamp"] > after]


def clear_events(job_id: str) -> None:
    """Remove all buffered events for a job (called on completion)."""
    _event_buffers.pop(job_id, None)


# ---------------------------------------------------------------------------
# Convenience helpers for pipeline.py
# ---------------------------------------------------------------------------

def emit_stage(job_id: str, stage: str, progress: int = 0, **extra: Any) -> None:
    """Emit a stage_change event."""
    publish_event(job_id, "stage_change", {"stage": stage, "progress": progress, **extra})


def emit_progress(job_id: str, stage: str, progress: int, **extra: Any) -> None:
    """Emit a progress update within a stage."""
    publish_event(job_id, "progress", {"stage": stage, "progress": progress, **extra})


def emit_clip_scored(job_id: str, clip_index: int, scores: dict, reason: str = "") -> None:
    """Emit when a clip finishes scoring."""
    publish_event(job_id, "clip_scored", {
        "clip_index": clip_index,
        "scores": scores,
        "reason": reason,
    })


def emit_clip_ready(job_id: str, clip_index: int, duration: float, final_score: float) -> None:
    """Emit when a clip file is fully processed and uploaded."""
    publish_event(job_id, "clip_ready", {
        "clip_index": clip_index,
        "duration": duration,
        "final_score": final_score,
    })


def emit_completed(job_id: str, total_clips: int, best_score: float, processing_time: float) -> None:
    """Emit job completion summary."""
    publish_event(job_id, "completed", {
        "total_clips": total_clips,
        "best_score": best_score,
        "processing_time_seconds": round(processing_time, 1),
    })


def emit_error(job_id: str, stage: str, message: str) -> None:
    """Emit an error event."""
    publish_event(job_id, "error", {"stage": stage, "message": message})
