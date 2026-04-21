"""File: workers/source_poller.py
Purpose: Periodic Celery task that polls all active connected sources for new content.
"""

from __future__ import annotations

import logging
from typing import Any

from db.repositories.autopilot import list_active_sources_for_polling
from services.source_ingestion import get_source_ingestion_service
from workers.celery_app import celery_app

# Redis lock configuration
POLLER_LOCK_KEY = "clipmind:poller:lock"
POLLER_LOCK_EXPIRE = 1800 # 30 minutes

logger = logging.getLogger(__name__)

@celery_app.task(name="workers.source_poller.poll_all_sources")
def poll_all_sources() -> dict[str, Any]:
    """Poller task with Redis locking to prevent overlapping runs."""
    # 1. Acquire Redis Lock
    redis_client = celery_app.backend.client
    lock_acquired = redis_client.set(POLLER_LOCK_KEY, "locked", ex=POLLER_LOCK_EXPIRE, nx=True)
    
    if not lock_acquired:
        logger.warning("[Autopilot] Another poller is already running. Skipping this cycle.")
        return {"status": "skipped", "reason": "lock_active"}
    
    try:
        sources = list_active_sources_for_polling()
        logger.info("[Autopilot] Polling %d active source(s)", len(sources))
        
        ingestion_service = get_source_ingestion_service()
        total_new_jobs = 0
        
        for source in sources:
            new_jobs = ingestion_service.poll_source(source)
            total_new_jobs += new_jobs
            
        return {
            "status": "success",
            "sources_polled": len(sources),
            "new_jobs_triggered": total_new_jobs
        }
    
    finally:
        # Release the lock
        redis_client.delete(POLLER_LOCK_KEY)

@celery_app.task(name="workers.source_poller.check_publish_queue")
def check_publish_queue() -> dict[str, Any]:
    """Check for scheduled clips that are ready to be published."""
    from db.repositories.autopilot import get_pending_publish_items
    from db.repositories.publish import update_publish_status
    
    pending_items = get_pending_publish_items()
    logger.info("Autopilot: Found %d pending publish item(s)", len(pending_items))
    
    published_count = 0
    failed_count = 0
    
    for item in pending_items:
        try:
            # Mark as processing
            update_publish_status(item["id"], "processing")
            
            # --- Simulated Publishing Logic ---
            # In a real app, this would call the TikTok/YouTube API
            # For Phase 4, we simulate success.
            logger.info(
                "Autopilot: Publishing clip %s from job %s to %s",
                item["clip_index"], item["job_id"], item["platform"]
            )
            
            # Simulate a 1-second "upload"
            import time
            time.sleep(1)
            
            mock_url = f"https://{item['platform']}.com/clips/mock_{item['id']}"
            update_publish_status(item["id"], "published", platform_url=mock_url)
            published_count += 1
            
        except Exception as exc:
            logger.error("Autopilot: Failed to publish item %s: %s", item["id"], exc)
            update_publish_status(item["id"], "failed", error_message=str(exc))
            failed_count += 1
            
    return {
        "processed": len(pending_items),
        "published": published_count,
        "failed": failed_count
    }
