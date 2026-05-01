"""File: api/routes/jobs.py
Purpose: Job status and clip retrieval endpoints. Provides endpoints to poll
         job processing status (/jobs/{job_id}/status) and retrieve clips
         (/jobs/{job_id}/clips) for a processing job.
"""

from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import text

from api.models.job import (
    ClipSummary,
    ErrorResponse,
    JobClipsResponse,
    JobListItem,
    JobListResponse,
    JobRecord,
    JobStatusResponse,
    JobRejectionResponse,
    ClipSearchResponse,
)
from db.repositories.jobs import get_job, list_jobs_for_user, update_job
from db.connection import engine
from services.discovery import get_discovery_service
from api.dependencies import get_current_user, AuthenticatedUser
from core.config import settings
from core.sparse import apply_sparse_filter


# Gap 71: Machine-readable error code registry
ERROR_CODES = {
    "job_not_found": "CM-4001",
    "job_not_ready": "CM-4002",
    "job_already_rejected": "CM-4003",
    "rejection_window_expired": "CM-4004",
    "completion_timestamp_missing": "CM-4005",
    "invalid_job_state": "CM-4006",
    "delete_failed": "CM-5001",
}


router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse, status_code=200)
def list_jobs(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0,
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return from JobListItem"),
) -> Any:
    jobs, total = list_jobs_for_user(user.user_id, limit=limit, offset=offset)
    
    # Gap 250: Apply sparse fieldsets
    job_list = [JobListItem.model_validate(job) for job in jobs]
    if fields:
        job_list = apply_sparse_filter(job_list, fields, JobListItem)
    
    return {
        "jobs": job_list,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def build_clip_summaries(job: JobRecord) -> list[ClipSummary] | None:
    if job.status != "completed" or not job.clips_json:
        return None
    return [
        ClipSummary(
            clip_index=clip.clip_index,
            clip_url=clip.clip_url,
            duration=clip.duration,
            final_score=clip.final_score,
            reason=clip.reason,
        )
        for clip in job.clips_json
    ]


def error_response(error: str, message: str, status_code: int) -> JSONResponse:
    # Gap 71: Attach machine-readable error code
    code = ERROR_CODES.get(error, "CM-5000")  # CM-5000 = unknown error
    payload = ErrorResponse(error=error, message=message, code=code)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.get("/{job_id}/status", response_model=JobStatusResponse, status_code=200)
def get_job_status(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return from JobStatusResponse"),
) -> Any:
    job = get_job(job_id, user_id=user.user_id)
    if job is None:
        return error_response("job_not_found", "No job found for the provided id.", 404)

    response_data = JobStatusResponse(
        job_id=job.id,
        status=job.status,
        failed_stage=job.failed_stage,
        error_message=job.error_message,
        clips=build_clip_summaries(job),
    )

    if fields:
        return apply_sparse_filter(response_data, fields, JobStatusResponse)

    return response_data


@router.get("/{job_id}/clips", response_model=JobClipsResponse, status_code=200)
def get_job_clips(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    fields: Optional[str] = Query(None, description="Comma-separated list of fields to return from ClipResult"),
) -> Any:
    job = get_job(job_id, user_id=user.user_id)
    if job is None:
        return error_response("job_not_found", "No job found for the provided id.", 404)
    if job.status != "completed":
        return error_response(
            "job_not_ready",
            f"Job is still processing. Current status: {job.status}",
            409,
        )

    clips = job.clips_json or []
    if fields:
        # Wrap in Pydantic models first if they are dicts
        clip_models = [ClipResult.model_validate(c) if isinstance(c, dict) else c for c in clips]
        clips = apply_sparse_filter(clip_models, fields, ClipResult)

    return {"job_id": job.id, "clips": clips}


@router.post("/{job_id}/reject", status_code=200)
def reject_job(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """Mark a job as rejected if within the 5-minute window after completion.
    
    Gap 82: Entire operation (update + audit log) runs inside a single transaction.
    """
    import logging
    _logger = logging.getLogger(__name__)

    job = get_job(job_id, user_id=user.user_id)
    if job is None:
        raise HTTPException(status_code=404, detail={"error": "job_not_found", "code": ERROR_CODES["job_not_found"]})
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail={"error": "invalid_job_state", "code": ERROR_CODES["invalid_job_state"], "message": "Only completed jobs can be rejected"})
    
    if job.is_rejected:
        return {"message": "Job already rejected", "job_id": job.id, "code": ERROR_CODES["job_already_rejected"]}
    
    # Check rejection window: completed_at < 5 minutes
    if not job.completed_at:
        raise HTTPException(status_code=400, detail={"error": "completion_timestamp_missing", "code": ERROR_CODES["completion_timestamp_missing"]})
    
    now = datetime.now(timezone.utc)
    comp_at = job.completed_at
    if comp_at.tzinfo is None:
        comp_at = comp_at.replace(tzinfo=timezone.utc)

    delta = (now - comp_at).total_seconds()
    if delta > 300:  # 5 minutes
        raise HTTPException(
            status_code=400,
            detail={
                "error": "rejection_window_expired",
                "code": ERROR_CODES["rejection_window_expired"],
                "message": f"Rejection window expired (elapsed: {int(delta)}s, max: 300s)"
            }
        )
    
    # Gap 82: Atomic transaction — update job + write audit log in a single commit
    from db.job_state import record_job_transition
    try:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE jobs SET is_rejected = 1, rejected_at = :ts WHERE id = :id"),
                {"ts": now.isoformat(), "id": str(job_id)},
            )
            # Inline audit log insertion to guarantee atomicity
            conn.execute(
                text("""
                    INSERT INTO job_state_events
                        (job_id, previous_status, new_status, stage, source, created_at)
                    VALUES
                        (:job_id, :prev, 'rejected', 'reject', 'user_action', :ts)
                """),
                {"job_id": str(job_id), "prev": job.status, "ts": now.isoformat()},
            )
    except Exception as exc:
        _logger.error("Failed to atomically reject job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="Failed to reject job")
    
    return JobRejectionResponse(
        status="success",
        message="Job rejected successfully.",
        job_id=job.id
    )


@router.get("/search", status_code=200)
async def semantic_search_clips(q: str, limit: int = 5) -> dict:
    """
    Search across all indexed clips using semantic intent.
    Gap: Scrubbing through hours of deep-dive podcasts to find a specific story.
    """
    discovery = get_discovery_service()
    # In a real app, we'd get user_id from the auth dependency
    # For MVP, we search globally or use the dev_mock_user_id
    results = await discovery.search_clips(query=q, limit=limit)
    
    return ClipSearchResponse(
        status="success",
        query=q,
        results=results
    )


@router.delete("/{job_id}", status_code=200)
async def delete_job_endpoint(
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Delete a job and its associated storage files (Gap 27).
    
    Order of operations:
    1. Fetch file URLs.
    2. Delete DB record (atomic).
    3. Cleanup files from storage (best effort).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # 1. Fetch job to get file URLs before deletion
    job = get_job(job_id, user_id=user.user_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Collect all file URLs to delete
    files_to_delete = []
    if job.source_video_url:
        files_to_delete.append(job.source_video_url)
    if job.audio_url:
        files_to_delete.append(job.audio_url)
    
    # Also collect clip output files from clips_json
    if job.clips_json:
        for clip in job.clips_json:
            if isinstance(clip, dict):
                url = clip.get("clip_url")
                if url:
                    files_to_delete.append(url)

    # 2. Delete from DB first (Critical order: DB record must be gone first)
    from db.repositories.jobs import delete_job
    success = delete_job(job_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete job record")
        
    # Gap 198: Clear stale vector indices to prevent ghost results
    try:
        from services.discovery import get_discovery_service
        discovery = get_discovery_service()
        await discovery.remove_job_from_index(job_id)
    except Exception as exc:
        logger.error(f"Failed to clear semantic vectors for deleted job {job_id}: {exc}")

    # 3. Clean up storage files (Best effort, individual try-except)
    from services.storage import storage_service
    
    deleted_count = 0
    for url in files_to_delete:
        try:
            await storage_service.delete_file(url)
            deleted_count += 1
        except Exception as exc:
            # We don't fail the whole request if one file fails to delete, 
            # but we log the orphan for manual cleanup if needed.
            logger.error(f"Orphaned file after job delete: {url} — {exc}")

    # Best-effort sweep for derived artifacts that may not be referenced
    # directly in the job row anymore.
    cleanup_roots = [
        settings.local_storage_dir / "clips",
        settings.local_storage_dir / "exports",
        settings.local_storage_dir / "audio",
        settings.local_storage_dir / "sources",
        settings.temp_dir,
    ]
    orphaned_count = 0
    for root in cleanup_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if job_id in path.name or job_id in path.as_posix():
                try:
                    path.unlink()
                    orphaned_count += 1
                except Exception as exc:
                    logger.error(f"Failed to delete orphaned artifact {path}: {exc}")

    return {
        "status": "success",
        "message": f"Job {job_id} and {deleted_count}/{len(files_to_delete)} referenced files deleted; {orphaned_count} orphaned artifacts removed.",
        "job_id": job_id
    }
