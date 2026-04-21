"""File: workers/maintenance_tasks.py
Purpose: Periodic maintenance tasks to keep the system healthy and recover from failures.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

@celery_app.task(name="workers.maintenance_tasks.reclaim_stale_jobs")
def reclaim_stale_jobs() -> int:
    """
    Find jobs stuck in 'processing' or 'queued' for > 45 minutes and mark as failed.
    Prevents 'ghost' jobs from cluttering the UI if a worker crashed mid-task.
    """
    timeout_threshold = datetime.now() - timedelta(minutes=45)
    
    query = text("""
        UPDATE jobs
        SET status = 'failed',
            failed_stage = 'pipeline',
            error_message = 'Job timed out: System reclaimed stale task',
            updated_at = NOW()
        WHERE status IN ('processing', 'queued')
          AND updated_at < :threshold
        RETURNING id
    """)
    
    try:
        # Import lazily so Celery beat can start even if the database is still
        # coming up. The task will fail gracefully at runtime instead of during
        # worker registration.
        from db.connection import engine

        with engine.begin() as connection:
            result = connection.execute(query, {"threshold": timeout_threshold})
            reclaimed_ids = [str(row[0]) for row in result.all()]
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
