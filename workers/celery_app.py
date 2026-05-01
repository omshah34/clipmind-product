"""File: workers/celery_app.py
Purpose: Celery configuration and Redis connection setup.
         Creates the Celery application instance and configures message broker.

Gap 368: Added get_jittered_countdown() utility — used by all task retry calls
         in pipeline.py instead of fixed countdown values.
Gap 331: Added gdpr_purge_expired_jobs to beat_schedule (runs nightly 2 AM).
"""

from __future__ import annotations

from core.logging_config import setup_logging
setup_logging()

import random   # Gap 368
import ssl

from celery import Celery
from celery.signals import before_task_publish, task_postrun, task_prerun

from core.config import settings
from core.request_context import current_context, reset_request_context, set_request_context


celery_app = Celery(
    "clipmind",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "workers.pipeline",
        "workers.webhooks",
        "workers.integrations",
        "workers.render_clips",
        "workers.analyze_sequences",
        "workers.publish_social",
        "workers.optimize_captions",
        "workers.track_signals",
        "workers.source_poller",
        "workers.dna_tasks",
        "workers.maintenance_tasks",
        "workers.analytics",
    ],
)

from kombu import Queue

_conf: dict = dict(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    result_expires=86400,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_retry=True,
    broker_connection_retry_delay=5,
    redis_backend_health_check_interval=30,
    worker_send_task_events=True,
    worker_heartbeat_interval=10,
    task_queue_max_priority=10,
    task_default_priority=5,
    task_queues=[
        Queue("celery", routing_key="celery"),
        Queue("pipeline_v2", routing_key="pipeline_v2", queue_arguments={"x-max-priority": 10}),
        Queue("renders_v2", routing_key="renders_v2", queue_arguments={"x-max-priority": 10}),
        Queue("publishing", routing_key="publishing"),
        Queue("dlq", routing_key="dlq"),
    ],
    broker_transport_options={
        "socket_timeout": settings.redis_socket_timeout,
        "socket_connect_timeout": settings.redis_socket_connect_timeout,
        "socket_keepalive": True,
        "socket_keepalive_intvl": 30,
        "retry_on_timeout": True,
        "max_retries": 5,
        "visibility_timeout": 7200,
        "queue_order_strategy": "priority",
    },
    task_routes={
        "workers.pipeline.*": {"queue": "pipeline_v2"},
        "workers.render_clips.*": {"queue": "renders_v2"},
        "workers.publish_social.*": {"queue": "publishing"},
    },
    task_reject_on_worker_lost=True,
    task_acks_late=True,
)

if settings.redis_url.startswith("rediss://"):
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    _conf["broker_use_ssl"] = _ssl_opts
    _conf["redis_backend_use_ssl"] = _ssl_opts

from celery.schedules import crontab

_conf["beat_schedule"] = {
    "sync_virality_performance": {
        "task": "workers.analytics.sync_all_active_performance",
        "schedule": crontab(hour="1,7,13,19", minute=0),
    },
    "generate_weekly_strategy_summary": {
        "task": "workers.dna_tasks.generate_all_executive_summaries",
        "schedule": crontab(day_of_week=0, hour=1, minute=30),
    },
    "poll_content_sources": {
        "task": "workers.source_poller.poll_all_sources",
        "schedule": 3600.0,
    },
    "reclaim_stale_jobs": {
        "task": "workers.maintenance_tasks.reclaim_stale_jobs",
        "schedule": 900.0,
    },
    "check_worker_watchdog": {
        "task": "workers.maintenance_tasks.check_worker_health",
        "schedule": 120.0,
    },
    "cleanup_orphaned_files": {
        "task": "workers.maintenance_tasks.cleanup_local_storage",
        "schedule": crontab(hour=3, minute=0),
    },
    # Gap 331: Nightly GDPR purge — hard-deletes soft-deleted rows older than
    # GDPR_RETENTION_DAYS. Runs at 2 AM to avoid overlap with 3 AM file cleanup.
    "gdpr_purge_expired_jobs": {
        "task": "workers.maintenance_tasks.purge_gdpr_expired_records",
        "schedule": crontab(hour=2, minute=0),
        "options": {"expires": 3600},  # skip if previous run still going
    },
}

celery_app.conf.update(**_conf)


# ---------------------------------------------------------------------------
# Gap 368: Jittered retry countdown utility
#
# PROBLEM (before this fix):
#   task_download  → raise self.retry(countdown=2 ** self.request.retries * 30)
#   task_transcribe → raise self.retry(countdown=60)
#   task_detect_clips → raise self.retry(countdown=60)
#   task_render    → raise self.retry(countdown=60)
#
#   When Groq goes down, ALL queued tasks fail simultaneously and retry at
#   exactly T+60s, hammering Groq again in a thundering herd. With Groq's
#   rate limits this means ALL tasks fail again → T+120s spike → repeat.
#
# FIX: Full-jitter exponential backoff (AWS retry guidance strategy).
#   Formula: uniform(0, min(max_delay, base * 2^attempt))
#   Each task gets a different random delay → load spreads naturally.
#
# USAGE in pipeline.py (replace every self.retry countdown):
#
#   from workers.celery_app import get_jittered_countdown
#
#   # Instead of: raise self.retry(exc=e, countdown=60)
#   raise self.retry(exc=e, countdown=get_jittered_countdown(self.request.retries))
#
#   # Instead of: raise self.retry(exc=e, countdown=2 ** self.request.retries * 30)
#   raise self.retry(exc=e, countdown=get_jittered_countdown(self.request.retries, base_delay=30.0))
# ---------------------------------------------------------------------------

def get_jittered_countdown(
    attempt: int,
    base_delay: float = 30.0,
    max_delay: float = 300.0,
) -> float:
    """
    Full-jitter exponential backoff for Celery task retries.

    attempt:    self.request.retries  (0 on first retry, 1 on second, etc.)
    base_delay: seconds for attempt=0 cap  (default 30s)
    max_delay:  hard ceiling in seconds    (default 300s = 5 min)

    Returns a float seconds value, randomised within [0, cap].
    """
    cap = min(max_delay, base_delay * (2 ** attempt))
    countdown = random.uniform(0.0, cap)
    return countdown


@before_task_publish.connect
def _inject_trace_headers(sender=None, headers=None, body=None, **kwargs):
    if headers is None:
        return
    context = current_context()
    headers.setdefault("clipmind_trace_id", context.trace_id or context.request_id)
    headers.setdefault("clipmind_request_id", context.request_id)
    headers.setdefault("clipmind_job_id", context.job_id)
    headers.setdefault("clipmind_user_id", context.user_id)


@task_prerun.connect
def _restore_trace_context(task_id=None, task=None, args=None, kwargs=None, **extra):
    request = getattr(task, "request", None)
    headers = getattr(request, "headers", {}) or {}
    tokens = set_request_context(
        request_id=headers.get("clipmind_request_id") or task_id,
        trace_id=headers.get("clipmind_trace_id") or task_id,
        job_id=headers.get("clipmind_job_id"),
        user_id=headers.get("clipmind_user_id"),
        source="celery",
    )
    if request is not None:
        setattr(request, "_clipmind_context_tokens", tokens)


@task_postrun.connect
def _clear_trace_context(task_id=None, task=None, args=None, kwargs=None, retval=None, state=None, **extra):
    request = getattr(task, "request", None)
    tokens = getattr(request, "_clipmind_context_tokens", None)
    if tokens is not None:
        reset_request_context(tokens)
