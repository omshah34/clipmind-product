"""File: workers/celery_app.py
Purpose: Celery configuration and Redis connection setup.
         Creates the Celery application instance and configures message broker.
"""

from __future__ import annotations

from core.logging_config import setup_logging
setup_logging()

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

# Base Celery config
from kombu import Queue

_conf: dict = dict(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Gap 202: Prevent Redis memory bloat by expiring results after 24h
    result_expires=86400,
    # Connection & retry settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_retry=True,
    broker_connection_retry_delay=5,
    redis_backend_health_check_interval=30,
    # Gap 206: Worker health & heartbeats
    worker_send_task_events=True,
    worker_heartbeat_interval=10,
    # Gap 209: Priority Queue Support
    task_queue_max_priority=10,
    task_default_priority=5,
    task_queues=[
        Queue("celery", routing_key="celery"),
        Queue("pipeline_v2", routing_key="pipeline_v2", queue_arguments={"x-max-priority": 10}),
        Queue("renders_v2", routing_key="renders_v2", queue_arguments={"x-max-priority": 10}),
        Queue("publishing", routing_key="publishing"),
        Queue("dlq", routing_key="dlq"),
    ],
    # Socket configuration - use settings from config.py
    broker_transport_options={
        "socket_timeout": settings.redis_socket_timeout,
        "socket_connect_timeout": settings.redis_socket_connect_timeout,
        "socket_keepalive": True,
        "socket_keepalive_intvl": 30,
        "retry_on_timeout": True,
        "max_retries": 5,
        # Gap 95: Prevent long-running render tasks (>1hr) from being re-queued
        # The visibility_timeout must exceed the longest expected task runtime.
        "visibility_timeout": 7200,  # 2 hours in seconds
        "queue_order_strategy": "priority",
    },
    # Gap 97: Route exhausted tasks to a Dead Letter Queue for manual inspection
    # Tasks that exceed max retries will be routed to the 'dlq' queue.
    task_routes={
        "workers.pipeline.*": {"queue": "pipeline_v2"},
        "workers.render_clips.*": {"queue": "renders_v2"},
        "workers.publish_social.*": {"queue": "publishing"},
    },
    # Gap 97: DLQ — when a task raises after all retries, Celery rejects it.
    # Setting task_reject_on_worker_lost ensures it goes to DLQ instead of disappearing.
    task_reject_on_worker_lost=True,
    task_acks_late=True,  # Required for reject_on_worker_lost to work correctly
)

# When using rediss:// (TLS), Celery requires explicit ssl_cert_reqs.
# Upstash provides valid TLS certs; CERT_NONE skips local CA verification and
# avoids the "ssl_cert_reqs missing" ValueError on startup.
if settings.redis_url.startswith("rediss://"):
    _ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE}
    _conf["broker_use_ssl"] = _ssl_opts
    _conf["redis_backend_use_ssl"] = _ssl_opts

# --- Periodic Task Schedule ---
from celery.schedules import crontab

# Gap 248: Explicitly stagger tasks to prevent midnight I/O spikes
_conf["beat_schedule"] = {
    "sync_virality_performance": {
        "task": "workers.analytics.sync_all_active_performance",
        "schedule": crontab(hour="1,7,13,19", minute=0), # Shifted away from midnight (1 AM, 7 AM, etc.)
    },
    "generate_weekly_strategy_summary": {
        "task": "workers.dna_tasks.generate_all_executive_summaries",
        "schedule": crontab(day_of_week=0, hour=1, minute=30), # Sunday 1:30 AM
    },
    "poll_content_sources": {
        "task": "workers.source_poller.poll_all_sources",
        "schedule": 3600.0, # Every hour
    },
    "reclaim_stale_jobs": {
        "task": "workers.maintenance_tasks.reclaim_stale_jobs",
        "schedule": 900.0, # Every 15 minutes
    },
    "check_worker_watchdog": {
        "task": "workers.maintenance_tasks.check_worker_health",
        "schedule": 120.0, # Every 2 minutes
    },
    "cleanup_orphaned_files": {
        "task": "workers.maintenance_tasks.cleanup_local_storage",
        "schedule": crontab(hour=3, minute=0), # Daily 3 AM
    },
}

celery_app.conf.update(**_conf)


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
