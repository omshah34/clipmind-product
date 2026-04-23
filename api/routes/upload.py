from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, File, UploadFile, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from api.models.job import (
    DirectUploadCompleteRequest,
    DirectUploadFailRequest,
    DirectUploadInitRequest,
    DirectUploadInitResponse,
    ErrorResponse,
    UploadResponse,
)
from api.dependencies.auth import get_current_user, AuthenticatedUser
from core.config import settings
from db.repositories.jobs import create_job
from db.repositories.jobs import get_job, update_job
from db.repositories.users import get_user_credits
from services.cost_tracker import estimate_job_cost
from services.storage import storage_service
from services.task_queue import dispatch_task
from services.video_processor import get_video_duration_seconds
from services import video_downloader
from workers.pipeline import process_job

class URLUploadRequest(BaseModel):
    url: str = Field(..., description="YouTube URL to import")
    brand_kit_id: UUID | None = None
    language: str | None = "en"


router = APIRouter(tags=["upload"])
ALLOWED_EXTENSIONS = {".mp4", ".mov"}


@dataclass
class UploadValidationError(Exception):
    error: str
    message: str


def validate_upload_constraints(
    filename: str,
    size_bytes: int,
    duration_seconds: float,
) -> None:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadValidationError(
            error="invalid_format",
            message="Accepted formats are MP4 and MOV.",
        )
    if size_bytes > 0 and size_bytes > settings.max_upload_size_bytes:
        raise UploadValidationError(
            error="file_too_large",
            message="File exceeds maximum allowed size of 2GB.",
        )
    if duration_seconds < settings.min_video_duration_seconds:
        raise UploadValidationError(
            error="duration_too_short",
            message="Video must be at least 2 minutes long.",
        )
    if duration_seconds > settings.max_video_duration_seconds:
        raise UploadValidationError(
            error="duration_too_long",
            message="Video exceeds maximum allowed duration of 90 minutes.",
        )


async def save_upload_to_temp(upload_file: UploadFile) -> tuple[Path, int]:
    extension = Path(upload_file.filename or "").suffix.lower() or ".mp4"
    temp_path = settings.temp_dir / f"upload_{uuid4().hex}{extension}"
    size_bytes = 0

    with temp_path.open("wb") as file_handle:
        while True:
            chunk = await upload_file.read(settings.chunk_upload_size_bytes)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > settings.max_upload_size_bytes:
                file_handle.close()
                temp_path.unlink(missing_ok=True)
                raise UploadValidationError(
                    error="file_too_large",
                    message="File exceeds maximum allowed size of 2GB.",
                )
            file_handle.write(chunk)

    await upload_file.close()
    return temp_path, size_bytes


def error_response(error: str, message: str, status_code: int) -> JSONResponse:
    payload = ErrorResponse(error=error, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump())


@router.post("/upload/direct/init", response_model=DirectUploadInitResponse, status_code=200)
def init_direct_upload(payload: DirectUploadInitRequest) -> DirectUploadInitResponse | JSONResponse:
    if not storage_service.is_cloud_storage_enabled():
        return error_response(
            "direct_upload_unavailable",
            "Direct upload requires Supabase storage. Use the legacy upload endpoint instead.",
            503,
        )

    try:
        validate_upload_constraints(
            payload.filename,
            payload.size_bytes,
            payload.duration_seconds,
        )
    except UploadValidationError as exc:
        return error_response(exc.error, exc.message, 400)

    object_path, signed_url, _token = storage_service.create_signed_upload_url("uploads", payload.filename)
    source_video_url = storage_service.build_public_url(object_path)
    estimated_cost_usd = estimate_job_cost(payload.duration_seconds)

    job = create_job(
        source_video_url=source_video_url,
        prompt_version=settings.clip_prompt_version,
        estimated_cost_usd=estimated_cost_usd,
        user_id=payload.user_id,
        brand_kit_id=payload.brand_kit_id,
        language=payload.language,
        status="uploading",
    )

    return DirectUploadInitResponse(
        job_id=job.id,
        status="uploading",
        created_at=job.created_at,
        upload_url=signed_url,
        source_video_url=source_video_url,
    )


@router.post("/upload/direct/complete", response_model=UploadResponse, status_code=200)
def complete_direct_upload(payload: DirectUploadCompleteRequest) -> UploadResponse | JSONResponse:
    job = get_job(payload.job_id)
    if not job:
        return error_response("job_not_found", "No job found for the provided id.", 404)

    update_job(job.id, status="uploaded")

    dispatch_task(
        process_job,
        str(job.id),
        fallback=lambda job_id: process_job.apply(args=(job_id,), throw=True),
        task_name="workers.pipeline.process_job",
    )

    return UploadResponse(
        job_id=job.id,
        status="uploaded",
        created_at=job.created_at,
    )


@router.post("/upload/direct/fail", status_code=200)
def fail_direct_upload(payload: DirectUploadFailRequest) -> dict[str, str]:
    job = get_job(payload.job_id)
    if not job:
        return {"status": "not_found"}

    update_job(
        job.id,
        status="failed",
        failed_stage="upload",
        error_message=payload.message,
    )
    return {"status": "failed"}


@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_video(
    file: UploadFile = File(...),
    user: AuthenticatedUser = Depends(get_current_user)
) -> UploadResponse | JSONResponse:
    if not file.filename:
        return error_response("invalid_file", "A video file is required.", 400)

    # Gap 74: Plan enforcement — check credits before starting job
    if get_user_credits(user.user_id) <= 0:
        return error_response(
            "insufficient_credits", 
            "You have 0 credits. Upgrade your plan to continue uploading.", 
            403
        )

    temp_path: Path | None = None
    try:
        temp_path, size_bytes = await save_upload_to_temp(file)
        duration_seconds = get_video_duration_seconds(temp_path)
        validate_upload_constraints(file.filename, size_bytes, duration_seconds)

        source_video_url = storage_service.upload_file(temp_path, "uploads", file.filename)
        estimated_cost_usd = estimate_job_cost(duration_seconds)
        job = create_job(
            source_video_url=source_video_url,
            prompt_version=settings.clip_prompt_version,
            estimated_cost_usd=estimated_cost_usd,
            user_id=str(user.user_id),
            language="en"
        )

        dispatch_task(
            process_job,
            str(job.id),
            fallback=lambda job_id: process_job.apply(args=(job_id,), throw=True),
            task_name="workers.pipeline.process_job",
        )

        return UploadResponse(
            job_id=job.id,
            status="uploaded",
            created_at=job.created_at,
        )

    except UploadValidationError as exc:
        return error_response(exc.error, exc.message, 400)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


@router.post("/upload/url", response_model=UploadResponse, status_code=200)
async def upload_url(
    payload: URLUploadRequest,
    user: AuthenticatedUser = Depends(get_current_user)
) -> UploadResponse | JSONResponse:
    """Download a video from YouTube and create a job."""
    
    # Gap 74: Plan enforcement
    if get_user_credits(user.user_id) <= 0:
        return error_response(
            "insufficient_credits", 
            "You have 0 credits. Upgrade your plan to continue uploading.", 
            403
        )

    # 1. Validate domain
    if not video_downloader.validate_url(payload.url):
        return error_response("invalid_domain", "Only YouTube links are allowed.", 400)

    temp_path: Path | None = None
    try:
        # 2. Extract Metadata
        try:
            info = video_downloader.get_video_info(payload.url)
            duration_seconds = info.get("duration", 0)
            title = info.get("title", f"youtube_{uuid4().hex[:8]}")
        except Exception as e:
            return error_response("metadata_failed", f"Could not fetch video info: {str(e)}", 400)

        # 3. Validation
        try:
            validate_upload_constraints(f"{title}.mp4", 0, duration_seconds)
        except UploadValidationError as exc:
            return error_response(exc.error, exc.message, 400)

        # 4. Download
        temp_path = settings.temp_dir / f"yt_{uuid4().hex}.mp4"
        try:
            video_downloader.download_video(payload.url, temp_path)
        except Exception as e:
            return error_response("download_failed", f"Failed to download video: {str(e)}", 500)

        # 4. Upload to Storage & Create Job
        source_video_url = storage_service.upload_file(temp_path, "uploads", f"{title}.mp4")
        estimated_cost_usd = estimate_job_cost(duration_seconds)
        
        job = create_job(
            source_video_url=source_video_url,
            prompt_version=settings.clip_prompt_version,
            estimated_cost_usd=estimated_cost_usd,
            user_id=str(user.user_id),
            brand_kit_id=payload.brand_kit_id,
            language=payload.language
        )

        dispatch_task(
            process_job,
            str(job.id),
            fallback=lambda job_id: process_job.apply(args=(job_id,), throw=True),
            task_name="workers.pipeline.process_job",
        )

        return UploadResponse(
            job_id=job.id,
            status="uploaded",
            created_at=job.created_at,
        )

    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
