import logging
from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

from api.dependencies import AuthenticatedUser, get_current_user
from api.models.performance import PerformanceSummary, PerformanceSyncStatusResponse
from api.response_utils import normalize_model
from db.repositories.performance import get_job_performance_summary
from db.repositories.performance_sync import (
    create_performance_sync_job,
    get_performance_sync_job,
    update_performance_sync_job,
)
from db.repositories.users import get_user_performance_summary
from services.performance_engine import get_performance_engine

logger = logging.getLogger(__name__)
performance_router = APIRouter(prefix="/performance", tags=["performance"])


class SyncResponse(BaseModel):
    job_id: str
    status: str
    retry_after: Optional[int] = None


@performance_router.get("/metrics")
def get_metrics(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    """Get aggregated metrics for the dashboard."""
    user_id = str(user.user_id)
    if start_date and end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be after start_date")

    return get_user_performance_summary(
        user_id,
        start_date=start_date,
        end_date=end_date,
    )


@performance_router.get("/jobs/{job_id}", response_model=PerformanceSummary, status_code=200)
def get_job_metrics(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> PerformanceSummary:
    summary = get_job_performance_summary(user.user_id, job_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Performance summary not found")
    return summary


@performance_router.get("/clips/{clip_id}")
def get_clip_performance(clip_id: str) -> dict:
    """Get detailed history for a specific clip."""
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
    user: AuthenticatedUser = Depends(get_current_user),
) -> SyncResponse:
    """Manually trigger a performance refresh with cooldown protection."""
    user_id = str(user.user_id)
    engine = get_performance_engine()

    if not engine.can_sync(user_id):
        raise HTTPException(
            status_code=429,
            detail={"message": "Sync cooldown active", "retry_after": 900},
        )

    job_id = uuid4().hex
    create_performance_sync_job(job_id, user.user_id, status="pending")

    def run_sync() -> None:
        try:
            update_performance_sync_job(job_id, status="processing")
            engine.sync_user_performance(user_id)
            update_performance_sync_job(job_id, status="complete")
        except Exception as exc:
            logger.error("Sync job %s failed: %s", job_id, exc)
            update_performance_sync_job(job_id, status="failed", error_message=str(exc))

    background_tasks.add_task(run_sync)
    return SyncResponse(job_id=job_id, status="pending")


@performance_router.get("/sync/{job_id}")
def get_sync_status(job_id: str) -> dict:
    """Poll for the status of a sync job."""
    sync_job = get_performance_sync_job(job_id)
    if sync_job is None:
        raise HTTPException(status_code=404, detail="Sync job not found")

    return normalize_model(PerformanceSyncStatusResponse, {
        "job_id": sync_job["job_id"],
        "status": sync_job["status"],
        "error_message": sync_job.get("error_message"),
    })
