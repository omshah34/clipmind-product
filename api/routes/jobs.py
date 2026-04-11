from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.models.job import (
    ClipSummary,
    ErrorResponse,
    JobClipsResponse,
    JobRecord,
    JobStatusResponse,
)
from db.queries import get_job


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
def get_job_status(job_id: UUID) -> JobStatusResponse | JSONResponse:
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
def get_job_clips(job_id: UUID) -> JobClipsResponse | JSONResponse:
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
