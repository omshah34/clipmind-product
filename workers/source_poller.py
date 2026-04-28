"""File: workers/source_poller.py
Purpose: Periodic Celery task that polls all active connected sources for new content.
"""

from __future__ import annotations

import logging
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import redis
from db.repositories.autopilot import list_active_sources_for_polling
from services.source_ingestion import get_source_ingestion_service
from workers.celery_app import celery_app
from core.redis_utils import RobustRedisLock
from core.config import settings

# Redis lock configuration
POLLER_LOCK_KEY = "clipmind:poller:lock"
POLLER_LOCK_EXPIRE = 1800 # 30 minutes

logger = logging.getLogger(__name__)

@celery_app.task(name="workers.source_poller.poll_all_sources")
def poll_all_sources() -> dict[str, Any]:
    """Poller task that fans out to process all active sources in parallel."""
    try:
        sources = list_active_sources_for_polling()
        logger.info("[Autopilot] Polling %d active source(s) using %d workers", len(sources), settings.poller_max_workers)
        
        ingestion_service = get_source_ingestion_service()
        total_new_jobs = 0
        
        # Gap 204: Fan out polling using a ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=settings.poller_max_workers) as executor:
                # Map future to source for exception isolation
                future_to_source = {
                    executor.submit(ingestion_service.poll_source, source): source 
                    for source in sources
                }
                
                for future in as_completed(future_to_source):
                    source = future_to_source[future]
                    source_id = source.get("id", "unknown")
                    try:
                        new_jobs = future.result()
                        total_new_jobs += new_jobs
                    except Exception as exc:
                        # Gap 204: Exception isolation per source
                        logger.error("[Autopilot] [source=%s] Polling failed: %s", source_id, exc, exc_info=True)
                
        return {
            "status": "success",
            "sources_polled": len(sources),
            "new_jobs_triggered": total_new_jobs
        }
    except Exception as e:
        logger.error("[Autopilot] Source poller failed: %s", e, exc_info=True)
        return {"status": "error", "message": str(e)}

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
