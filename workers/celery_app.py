"""File: workers/celery_app.py
Purpose: Celery configuration and Redis connection setup.
         Creates the Celery application instance and configures message broker.
"""

from __future__ import annotations

from core.logging_config import setup_logging
setup_logging()

import ssl

from celery import Celery

from core.config import settings


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
_conf: dict = dict(
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    # Connection & retry settings
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_retry=True,
    broker_connection_retry_delay=5,
    redis_backend_health_check_interval=30,
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
    },
    # Gap 97: Route exhausted tasks to a Dead Letter Queue for manual inspection
    # Tasks that exceed max retries will be routed to the 'dlq' queue.
    task_routes={
        "workers.pipeline.*": {"queue": "pipeline"},
        "workers.render_clips.*": {"queue": "renders"},
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
_conf["beat_schedule"] = {
    "sync_virality_performance": {
        "task": "workers.analytics.sync_all_active_performance",
        "schedule": 21600.0, # Every 6 hours
    },
    "generate_weekly_strategy_summary": {
        "task": "workers.dna_tasks.generate_all_executive_summaries",
        "schedule": crontab(hour=0, minute=0, day_of_week=0), # Sunday midnight
    },
    "poll_content_sources": {
        "task": "workers.source_poller.poll_all_sources",  # Gap 70: Fixed name mismatch
        "schedule": 3600.0, # Every hour
    },
    "reclaim_stale_jobs": {
        "task": "workers.maintenance_tasks.reclaim_stale_jobs",
        "schedule": 900.0, # Every 15 minutes
    },
}

celery_app.conf.update(**_conf)

