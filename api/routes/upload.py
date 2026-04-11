from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from api.models.job import ErrorResponse, UploadResponse
from config import settings
from db.queries import create_job
from services.cost_tracker import estimate_job_cost
from services.storage import storage_service
from services.video_processor import get_video_duration_seconds
from workers.pipeline import process_job


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
    if size_bytes > settings.max_upload_size_bytes:
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


@router.post("/upload", response_model=UploadResponse, status_code=200)
async def upload_video(file: UploadFile = File(...)) -> UploadResponse | JSONResponse:
    if not file.filename:
        return error_response("invalid_file", "A video file is required.", 400)

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
        )

        process_job.delay(str(job.id))

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
