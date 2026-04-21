"""File: workers/analytics.py
Purpose: Periodic background tasks for platform performance syncing.
"""

from __future__ import annotations

import logging
from workers.celery_app import celery_app
from services.performance_engine import get_performance_engine
from db.queries import get_all_users_with_active_platforms

logger = logging.getLogger(__name__)

@celery_app.task(name="workers.analytics.sync_all_active_performance")
def sync_all_active_performance() -> dict:
    """
    Scheduled task: Polls platform APIs for all users with active connections.
    Transitions ClipMind from a 'generation tool' to an 'intelligence platform'.
    """
    engine = get_performance_engine()
    user_ids = get_all_users_with_active_platforms()
    
    summary = {
        "users_hit": len(user_ids),
        "total_processed": 0,
        "total_errors": 0,
        "milestones_detected": 0
    }
    
    logger.info("[analytics] Starting global performance sync for %d users", len(user_ids))
    
    for uid in user_ids:
        try:
            # Note: sync_user_performance iterates clips for that user
            res = engine.sync_user_performance(uid)
            
            if res.get("status") == "error":
                logger.info("[analytics] User %s sync skipped: %s", uid, res.get("message"))
                continue
                
            summary["total_processed"] += res.get("processed", 0)
            summary["total_errors"] += res.get("errors", 0)
            # engine doesn't return milestones count in sync_user_performance yet, 
            # but they are recorded via alerts. We could add count if needed.
            
        except Exception as exc:
            logger.error("[analytics] Critical failure for user %s: %s", uid, exc)
            summary["total_errors"] += 1
            
    logger.info("[analytics] Global sync complete: %s", summary)
    return summary
