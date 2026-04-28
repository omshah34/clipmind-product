"""File: workers/maintenance_tasks.py
Purpose: Periodic maintenance tasks to keep the system healthy and recover from failures.
"""

from __future__ import annotations

import logging
import os
import platform
import time
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(
    name="workers.maintenance_tasks.reclaim_stale_jobs",
    soft_time_limit=300,
    time_limit=330
)
def reclaim_stale_jobs() -> int:
    """
    Find jobs stuck in 'processing', 'queued', or 'uploading' for > 45 minutes and mark as failed.
    Prevents 'ghost' jobs from cluttering the UI if a worker crashed mid-task.
    Dialect-aware: works on both PostgreSQL and SQLite.
    """
    timeout_threshold = datetime.now(timezone.utc) - timedelta(minutes=45)

    try:
        from db.connection import engine

        is_postgres = engine.dialect.name == "postgresql"

        with engine.begin() as connection:
            if is_postgres:
                # Postgres: single atomic UPDATE ... RETURNING
                result = connection.execute(
                    text("""
                        UPDATE jobs
                        SET status = 'failed',
                            failed_stage = 'pipeline',
                            error_message = 'Job timed out: System reclaimed stale task',
                            updated_at = NOW()
                        WHERE status IN ('processing', 'queued', 'uploading')
                          AND updated_at < :threshold
                        RETURNING id
                    """),
                    {"threshold": timeout_threshold},
                )
                reclaimed_ids = [str(row[0]) for row in result.all()]
            else:
                # SQLite: SELECT first, then UPDATE (no RETURNING support)
                stale = connection.execute(
                    text("""
                        SELECT id FROM jobs
                        WHERE status IN ('processing', 'queued', 'uploading')
                          AND updated_at < :threshold
                    """),
                    {"threshold": timeout_threshold.isoformat()},
                ).all()
                reclaimed_ids = [str(row[0]) for row in stale]
                if reclaimed_ids:
                    # Bind list via IN — safe because IDs are UUIDs/hex strings
                    placeholders = ", ".join(f":id{i}" for i in range(len(reclaimed_ids)))
                    params = {f"id{i}": rid for i, rid in enumerate(reclaimed_ids)}
                    params["ts"] = datetime.now(timezone.utc).isoformat()
                    connection.execute(
                        text(f"""
                            UPDATE jobs
                            SET status = 'failed',
                                failed_stage = 'pipeline',
                                error_message = 'Job timed out: System reclaimed stale task',
                                updated_at = :ts
                            WHERE id IN ({placeholders})
                        """),
                        params,
                    )

    except SQLAlchemyError as exc:
        logger.warning("Maintenance: skipped stale-job reclamation due to database error: %s", exc)
        return 0

    if reclaimed_ids:
        logger.warning(
            "Maintenance: Reclaimed %d stale jobs: %s",
            len(reclaimed_ids),
            ", ".join(reclaimed_ids)
        )
    return len(reclaimed_ids)


@celery_app.task(
    name="workers.maintenance_tasks.cleanup_local_storage",
    soft_time_limit=600,
    time_limit=660
)
def cleanup_local_storage() -> int:
    """
    Remove temporary files older than 24 hours from local storage.
    Prevents disk exhaustion from failed/interrupted jobs (Gap 43).
    """
    from core.config import settings
    import os
    import time
    
    count = 0
    now = time.time()
    max_age = 24 * 3600 # 24 hours
    
    # Directories to scan
    dirs = [
        settings.temp_dir,
        settings.local_storage_dir / "uploads",
        settings.local_storage_dir / "audio",
        settings.local_storage_dir / "clips"
    ]
    
    for d in dirs:
        if not d.exists():
            continue
            
        for f in d.iterdir():
            if f.is_file():
                age = now - f.stat().st_mtime
                if age > max_age:
                    try:
                        f.unlink()
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to delete orphaned file %s: %s", f, e)
                        
    if count > 0:
        logger.info("Maintenance: Cleaned up %d orphaned files from local storage", count)
    return count

@celery_app.task(
    name="workers.maintenance_tasks.check_worker_health",
    soft_time_limit=60,
    time_limit=90
)
def check_worker_health() -> dict:
    """
    Gap 206: Active Worker Watchdog.
    Pings workers and inspects active tasks to identify unresponsive/zombie states.
    """
    # 1. Reachability Check
    pings = None
    for attempt in range(2):
        inspector = celery_app.control.inspect()
        pings = inspector.ping()
        if pings:
            break
        if attempt == 0:
            time.sleep(1)

    if not pings:
        stats = celery_app.control.inspect().stats()
        if stats:
            logger.warning(
                "WATCHDOG: ping returned no responses, but %d worker(s) reported stats; treating as transient inspect failure.",
                len(stats),
            )
            return {"status": "degraded", "workers_online": len(stats), "reason": "ping_transient"}
        if os.getenv("ENVIRONMENT", "development") != "production" or platform.system() == "Windows":
            logger.info("WATCHDOG: No workers responded to ping after retry; treating as degraded in local/non-production mode.")
            return {"status": "degraded", "reason": "no_workers_local"}
        logger.critical("WATCHDOG: No workers responded to ping after retry.")
        return {"status": "critical", "reason": "no_workers"}

    # 2. Progress Check (Active Tasks)
    active_tasks = celery_app.control.inspect().active()
    revoked_count = 0
    now = datetime.now(timezone.utc).timestamp()

    if active_tasks:
        for worker, tasks in active_tasks.items():
            for task in tasks:
                # task['time_start'] is epoch seconds when task was received
                start_time = task.get('time_start')
                if not start_time:
                    continue
                
                # Baseline from task name or default
                name = task.get('name', '')
                baseline = 1800 if 'pipeline' in name else 600
                
                runtime = now - start_time
                if runtime > (baseline * 2.0):
                    logger.critical(
                        "WATCHDOG: Task %s [%s] on %s has been running for %ds (limit %ds). Revoking with SIGKILL.",
                        name, task['id'], worker, int(runtime), baseline
                    )
                    celery_app.control.revoke(task['id'], terminate=True, signal='SIGKILL')
                    revoked_count += 1
                elif runtime > (baseline * 1.5):
                    logger.warning(
                        "WATCHDOG: Task %s [%s] on %s is exceeding soft limit (runtime %ds, baseline %ds).",
                        name, task['id'], worker, int(runtime), baseline
                    )

    return {
        "status": "ok",
        "workers_online": len(pings),
        "revoked_zombies": revoked_count
    }
