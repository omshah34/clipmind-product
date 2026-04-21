"""File: api/routes/jobs.py
Purpose: Job status and clip retrieval endpoints. Provides endpoints to poll
         job processing status (/jobs/{job_id}/status) and retrieve clips
         (/jobs/{job_id}/clips) for a processing job.
"""

from __future__ import annotations

from uuid import UUID

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from api.models.job import (
    ClipSummary,
    ErrorResponse,
    JobClipsResponse,
    JobRecord,
    JobStatusResponse,
)
from db.repositories.jobs import get_job, update_job


router = APIRouter(prefix="/jobs", tags=["jobs"])


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
    payload = ErrorResponse(error=error, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.get("/{job_id}/status", response_model=JobStatusResponse, status_code=200)
def get_job_status(job_id: UUID) -> JobStatusResponse:
    job = get_job(job_id)
    if job is None:
        return error_response("job_not_found", "No job found for the provided id.", 404)

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        failed_stage=job.failed_stage,
        error_message=job.error_message,
        clips=build_clip_summaries(job),
    )


@router.get("/{job_id}/clips", response_model=JobClipsResponse, status_code=200)
def get_job_clips(job_id: UUID) -> JobClipsResponse:
    job = get_job(job_id)
    if job is None:
        return error_response("job_not_found", "No job found for the provided id.", 404)
    if job.status != "completed":
        return error_response(
            "job_not_ready",
            f"Job is still processing. Current status: {job.status}",
            409,
        )

    return JobClipsResponse(job_id=job.id, clips=job.clips_json or [])


@router.post("/{job_id}/reject", status_code=200)
def reject_job(job_id: UUID) -> dict:
    """Mark a job as rejected if within the 5-minute window after completion."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Only completed jobs can be rejected")
    
    if job.is_rejected:
        return {"message": "Job already rejected", "job_id": job.id}
    
    # Check rejection window: completed_at < 5 minutes
    if not job.completed_at:
        raise HTTPException(status_code=400, detail="Job completion timestamp missing")
    
    # Ensure both are UTC if necessary, but here we assume DB stores correctly
    now = datetime.now(timezone.utc)
    # Pydantic models usually handles timezone if DB is TIMESTAMPTZ
    comp_at = job.completed_at
    if comp_at.tzinfo is None:
        comp_at = comp_at.replace(tzinfo=timezone.utc)

    delta = (now - comp_at).total_seconds()
    if delta > 300: # 5 minutes
        raise HTTPException(
            status_code=400, 
            detail=f"Rejection window expired (elapsed: {int(delta)}s, max: 300s)"
        )
    
    # Mark as rejected
    update_job(
        job_id, 
        is_rejected=True, 
        rejected_at=datetime.now(timezone.utc)
    )
    
    return {
        "status": "success",
        "message": "Job rejected successfully. Mock credit refund logged.",
        "job_id": job.id
    }
