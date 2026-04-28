"""Utilities for dispatching Celery tasks safely.

The app uses Redis-backed Celery for background jobs, but development
environments may not always have Redis available. These helpers allow the
API to degrade gracefully instead of surfacing Celery connection errors.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import redis

from core.config import settings

logger = logging.getLogger(__name__)


def is_redis_available() -> bool:
    """Return True when the configured Redis broker responds to PING."""
    try:
        client = redis.Redis.from_url(
            settings.redis_url,
            socket_timeout=min(settings.redis_socket_timeout, 3),
            socket_connect_timeout=min(settings.redis_socket_connect_timeout, 3),
            decode_responses=True,
        )
        return bool(client.ping())
    except Exception:
        return False


def _resolve_task(task: Any) -> Any:
    """Return a Celery task object for a task instance or registered task name."""
    if isinstance(task, str):
        from workers.celery_app import celery_app

        resolved = celery_app.tasks.get(task)
        if resolved is None:
            raise KeyError(f"Unknown Celery task: {task}")
        return resolved
    return task


def dispatch_task(
    task: Any,
    *args: Any,
    fallback: Callable[..., Any] | None = None,
    task_name: str | None = None,
    **kwargs: Any,
) -> Any:
    """Send a task to Celery, or run the fallback when dispatch fails."""
    label = task_name or getattr(task, "name", "celery-task")

    try:
        resolved_task = _resolve_task(task)
        return resolved_task.delay(*args, **kwargs)
    except Exception as exc:
        if fallback is not None:
            logger.warning("[%s] Task dispatch failed; running inline fallback.", label)
            return fallback(*args, **kwargs)

        logger.exception("[%s] Task dispatch failed and no fallback was provided.", label)
        raise RuntimeError(f"[{label}] Task dispatch failed") from exc
