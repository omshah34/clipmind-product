import logging
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from pydantic import BaseModel

from db.repositories.performance import (
    get_user_performance_summary,
    list_performance_alerts,
    upsert_clip_performance
)
from services.performance_engine import get_performance_engine
from workers.source_poller import check_publish_queue # Actually we'll add sync_performance_task there
from api.dependencies import get_current_user, AuthenticatedUser

logger = logging.getLogger(__name__)
performance_router = APIRouter(prefix="/performance", tags=["performance"])

# --- Models ---
class SyncResponse(BaseModel):
    job_id: str
    status: str
    retry_after: Optional[int] = None

# --- In-memory sync status (MVP) ---
# In production, this would be in Redis
sync_jobs = {}

@performance_router.get("/metrics")
def get_metrics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """Get aggregated metrics for the dashboard."""
    user_id = str(user.user_id)
    summary = get_user_performance_summary(user_id)
    return summary


@performance_router.get("/clips/{clip_id}")
def get_clip_performance(clip_id: str) -> dict:
    """Get detailed history for a specific clip."""
    # We query the clip_performance table for historical data
    from db.repositories.performance import engine
    from sqlalchemy import text
    
    query = text("SELECT * FROM clip_performance WHERE id = :id")
    with engine.connect() as connection:
        row = connection.execute(query, {"id": clip_id}).fetchone()
    
    if not row:
        return {"empty_state": True}
        
    return dict(row._mapping)


@performance_router.post("/sync", status_code=202)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user)
) -> SyncResponse:
    """Manually trigger a performance refresh with cooldown protection."""
    user_id = str(user.user_id)
    engine = get_performance_engine("mock")
    
    if not engine.can_sync(user_id):
        # Calculate retry_after (15 mins cooldown)
        # For this MVP, we return a generic 900 seconds
        raise HTTPException(
            status_code=429, 
            detail={"message": "Sync cooldown active", "retry_after": 900}
        )

    job_id = f"sync_{UUID(int=timedelta(seconds=datetime.now().timestamp()).seconds % (2**128))}"
    sync_jobs[job_id] = "pending"
    
    # Run sync in background
    def run_sync():
        try:
            engine.sync_user_performance(user_id)
            sync_jobs[job_id] = "complete"
        except Exception as e:
            logger.error("Sync job %s failed: %s", job_id, e)
            sync_jobs[job_id] = "failed"

    background_tasks.add_task(run_sync)
    
    return SyncResponse(job_id=job_id, status="pending")


@performance_router.get("/sync/{job_id}")
def get_sync_status(job_id: str) -> dict:
    """Poll for the status of a sync job."""
    status = sync_jobs.get(job_id, "unknown")
    if status == "unknown":
        raise HTTPException(status_code=404, detail="Sync job not found")
    return {"job_id": job_id, "status": status}
