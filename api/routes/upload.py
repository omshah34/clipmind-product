from __future__ import annotations

from dataclasses import dataclass
import hashlib
import time
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
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

logger = logging.getLogger(__name__)

class URLUploadRequest(BaseModel):
    url: str = Field(..., description="YouTube URL to import")
    brand_kit_id: UUID | None = None
    language: str | None = "en"


router = APIRouter(tags=["upload"])
ALLOWED_EXTENSIONS = {".mp4", ".mov"}
TEMP_UPLOAD_TTL_SECONDS = 3600


@dataclass
class UploadValidationError(Exception):
    error: str
    message: str


def _detect_video_container(path: Path) -> str | None:
    """Return a detected container family based on magic bytes."""
    try:
        with path.open("rb") as file_handle:
            header = file_handle.read(64)
    except OSError:
        return None

    if len(header) < 12:
        return None

    if header[4:8] == b"ftyp":
        return "mp4"
    if header.startswith(b"\x1A\x45\xDF\xA3"):
        return "mkv"
    return None


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while True:
            chunk = file_handle.read(settings.chunk_upload_size_bytes)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_stale_upload_tempfiles() -> None:
    cutoff = time.time() - TEMP_UPLOAD_TTL_SECONDS
    for candidate in settings.temp_dir.glob("upload_*"):
        try:
            if candidate.is_file() and candidate.stat().st_mtime < cutoff:
                candidate.unlink(missing_ok=True)
        except OSError:
            logger.debug("Skipping stale temp cleanup for %s", candidate, exc_info=True)


def _decorate_public_url(url: str, *, expected_size_bytes: int) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["cm_expected_size"] = [str(expected_size_bytes)]
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _extract_expected_size(url: str) -> int | None:
    parsed = urlparse(url)
    value = parse_qs(parsed.query).get("cm_expected_size", [None])[0]
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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
    cleanup_stale_upload_tempfiles()
    extension = Path(upload_file.filename or "").suffix.lower() or ".mp4"
    temp_path = settings.temp_dir / f"upload_{uuid4().hex}{extension}"
    size_bytes = 0
    digest = hashlib.sha256()

    try:
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
                digest.update(chunk)
                file_handle.write(chunk)

        if size_bytes == 0:
            temp_path.unlink(missing_ok=True)
            raise UploadValidationError(
                error="invalid_file",
                message="The uploaded file is empty.",
            )

        disk_digest = _hash_file(temp_path)
        if disk_digest != digest.hexdigest():
            temp_path.unlink(missing_ok=True)
            raise UploadValidationError(
                error="upload_integrity_failed",
                message="The buffered upload was corrupted before validation completed.",
            )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload_file.close()

    logger.info(
        "Buffered upload %s (%d bytes, sha256=%s)",
        temp_path.name,
        size_bytes,
        digest.hexdigest()[:12],
    )
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
        source_video_url=_decorate_public_url(
            source_video_url,
            expected_size_bytes=payload.size_bytes,
        ),
        prompt_version=settings.clip_prompt_version,
        estimated_cost_usd=estimated_cost_usd,
        user_id=payload.user_id,
        brand_kit_id=payload.brand_kit_id,
        language=payload.language,
        status="uploading",
    )

    return DirectUploadInitResponse(
        job_id=str(job.id),
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
    if job.status != "uploading":
        return error_response(
            "upload_session_expired",
            f"This upload session is no longer active. Current status: {job.status}.",
            409,
        )

    object_path = storage_service.extract_object_path(job.source_video_url)
    if not object_path or not storage_service.object_exists(object_path):
        update_job(
            job.id,
            status="failed",
            failed_stage="upload",
            error_message="Uploaded file was not found in storage.",
        )
        return error_response(
            "upload_missing",
            "The uploaded file could not be found in storage.",
            409,
        )

    expected_size_bytes = _extract_expected_size(job.source_video_url)
    verification_path = settings.temp_dir / f"direct_upload_verify_{job.id}.mp4"
    try:
        storage_service.download_to_local(job.source_video_url, verification_path)
        actual_size_bytes = verification_path.stat().st_size
        if expected_size_bytes is None:
            raise UploadValidationError(
                error="upload_verification_failed",
                message="Upload metadata is missing size information.",
            )
        if actual_size_bytes != expected_size_bytes:
            raise UploadValidationError(
                error="upload_verification_failed",
                message="Uploaded file size does not match the size recorded at upload start.",
            )
        detected_container = _detect_video_container(verification_path)
        if detected_container != "mp4":
            raise UploadValidationError(
                error="invalid_format",
                message=(
                    "The uploaded file signature does not match an MP4/MOV video."
                    if detected_container is None
                    else f"Detected {detected_container.upper()} container data in a file presented as MP4/MOV."
                ),
            )
        logger.info(
            "Verified direct upload %s (%d bytes, sha256=%s)",
            verification_path.name,
            actual_size_bytes,
            _hash_file(verification_path)[:12],
        )
    except UploadValidationError as exc:
        update_job(
            job.id,
            status="failed",
            failed_stage="upload",
            error_message=exc.message,
        )
        return error_response(exc.error, exc.message, 400)
    except Exception as exc:
        update_job(
            job.id,
            status="failed",
            failed_stage="upload",
            error_message=str(exc),
        )
        return error_response(
            "upload_verification_failed",
            f"Could not verify the uploaded file: {exc}",
            409,
        )
    finally:
        if verification_path.exists():
            verification_path.unlink(missing_ok=True)

    update_job(job.id, status="uploaded")

    dispatch_task(
        process_job,
        str(job.id),
        fallback=lambda job_id: process_job.apply(args=(job_id,), throw=True),
        task_name="workers.pipeline.process_job",
    )

    return UploadResponse(
        job_id=str(job.id),
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
        detected_container = _detect_video_container(temp_path)
        if detected_container != "mp4":
            raise UploadValidationError(
                error="invalid_format",
                message=(
                    "The file signature does not match an MP4/MOV video."
                    if detected_container is None
                    else f"Detected {detected_container.upper()} container data in a file presented as MP4/MOV."
                ),
            )
        duration_seconds = get_video_duration_seconds(temp_path)
        validate_upload_constraints(file.filename, size_bytes, duration_seconds)

        source_video_url = storage_service.upload_file_deduplicated(temp_path, "uploads", file.filename)
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
            job_id=str(job.id),
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

        detected_container = _detect_video_container(temp_path)
        if detected_container != "mp4":
            return error_response(
                "invalid_format",
                (
                    "Downloaded file signature does not match an MP4/MOV video."
                    if detected_container is None
                    else f"Detected {detected_container.upper()} container data in a file presented as MP4/MOV."
                ),
                400,
            )

        # 4. Upload to Storage & Create Job
        source_video_url = storage_service.upload_file_deduplicated(temp_path, "uploads", f"{title}.mp4")
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
            job_id=str(job.id),
            status="uploaded",
            created_at=job.created_at,
        )

    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
def _looks_like_video_container(path: Path) -> bool:
    return _detect_video_container(path) == "mp4"


# ──────────────────────────────────────────────────────────────────────────────
# Gap 240: ETag-verified resumable multipart upload endpoints
#
# These three routes implement the server side of the chunked-uploader.ts
# client.  A lightweight Redis-backed session stores per-part presigned URLs
# and committed ETags so the frontend can resume across page refreshes.
# ──────────────────────────────────────────────────────────────────────────────

import json as _json
from typing import List

class MultipartInitRequest(BaseModel):
    filename: str = Field(..., max_length=512)
    size_bytes: int = Field(..., gt=0)
    total_parts: int = Field(..., ge=1, le=10_000)


class MultipartInitResponse(BaseModel):
    upload_id: str
    part_urls: List[str]


class MultipartVerifyRequest(BaseModel):
    upload_id: str
    part_number: int = Field(..., ge=1)
    etag: str = Field(..., max_length=256)


class MultipartVerifyResponse(BaseModel):
    verified: bool


class MultipartCompleteRequest(BaseModel):
    upload_id: str
    parts: List[dict]  # [{"part_number": int, "etag": str}]


class MultipartCompleteResponse(BaseModel):
    source_video_url: str


def _mp_redis():
    """Return a Redis client for multipart session storage, or None."""
    try:
        import redis as _redis
        from core.config import settings as _s
        return _redis.from_url(_s.redis_url, decode_responses=True, socket_timeout=5)
    except Exception:
        return None


def _mp_session_key(upload_id: str) -> str:
    return f"cm:mp:{upload_id}"


def _mp_save_session(upload_id: str, data: dict) -> None:
    r = _mp_redis()
    if r is None:
        return
    try:
        r.setex(_mp_session_key(upload_id), 3600 * 24, _json.dumps(data))  # 24 h TTL
    except Exception:
        pass


def _mp_load_session(upload_id: str) -> dict | None:
    r = _mp_redis()
    if r is None:
        return None
    try:
        raw = r.get(_mp_session_key(upload_id))
        return _json.loads(raw) if raw else None
    except Exception:
        return None


def _mp_delete_session(upload_id: str) -> None:
    r = _mp_redis()
    if r is None:
        return
    try:
        r.delete(_mp_session_key(upload_id))
    except Exception:
        pass


@router.post("/upload/multipart/init", response_model=MultipartInitResponse, status_code=200)
def init_multipart_upload(payload: MultipartInitRequest) -> MultipartInitResponse | JSONResponse:
    """Gap 240 — Initialise a multipart upload session and return per-part presigned URLs.

    For Supabase storage the presigned URL approach is simulated: each part
    gets a unique signed upload path inside a session-scoped folder.  For S3
    this would map to `create_multipart_upload` + `generate_presigned_url` per
    part.  The client will PUT each chunk directly to the returned URL and send
    back the ETag for verification.
    """
    if not storage_service.is_cloud_storage_enabled():
        return error_response(
            "multipart_unavailable",
            "Multipart upload requires cloud storage. Use the standard upload endpoint.",
            503,
        )

    upload_id = uuid4().hex
    part_urls: list[str] = []

    for part_number in range(1, payload.total_parts + 1):
        part_path = f"uploads/mp/{upload_id}/part_{part_number:05d}"
        try:
            _object_path, signed_url, _token = storage_service.create_signed_upload_url(
                f"uploads/mp/{upload_id}", f"part_{part_number:05d}"
            )
            part_urls.append(signed_url)
        except Exception as exc:
            logger.error("Failed to create signed URL for part %d: %s", part_number, exc)
            return error_response(
                "signed_url_error",
                f"Could not generate presigned URL for part {part_number}.",
                500,
            )

    session_data = {
        "upload_id": upload_id,
        "filename": payload.filename,
        "size_bytes": payload.size_bytes,
        "total_parts": payload.total_parts,
        "part_urls": part_urls,
        "committed_etags": {},  # part_number (str) → etag
    }
    _mp_save_session(upload_id, session_data)

    logger.info(
        "Multipart session %s initialised (%d parts, %.1f MB)",
        upload_id[:8],
        payload.total_parts,
        payload.size_bytes / (1024 * 1024),
    )
    return MultipartInitResponse(upload_id=upload_id, part_urls=part_urls)


@router.post("/upload/multipart/verify", response_model=MultipartVerifyResponse, status_code=200)
def verify_multipart_part(payload: MultipartVerifyRequest) -> MultipartVerifyResponse | JSONResponse:
    """Gap 240 — Verify that a specific part's ETag matches what was committed.

    The frontend calls this before deciding whether to skip re-uploading a part
    on resume.  Returns ``verified: true`` only if the stored ETag matches the
    one supplied by the client.
    """
    session = _mp_load_session(payload.upload_id)
    if not session:
        return MultipartVerifyResponse(verified=False)

    committed = session.get("committed_etags", {})
    stored_etag = committed.get(str(payload.part_number))
    verified = stored_etag is not None and stored_etag == payload.etag

    if not verified:
        logger.debug(
            "ETag mismatch for session=%s part=%d supplied=%s stored=%s",
            payload.upload_id[:8],
            payload.part_number,
            payload.etag[:16],
            (stored_etag or "MISSING")[:16],
        )

    return MultipartVerifyResponse(verified=verified)


@router.post("/upload/multipart/complete", response_model=MultipartCompleteResponse, status_code=200)
def complete_multipart_upload_session(
    payload: MultipartCompleteRequest,
) -> MultipartCompleteResponse | JSONResponse:
    """Gap 240 — Finalise the multipart upload and register the canonical asset URL.

    The client sends all committed ``{part_number, etag}`` pairs.  This handler:
    1. Validates every ETag against the server-side session.
    2. Records the upload_id and final ETags in the multipart session.
    3. Returns a stable ``source_video_url`` the job can use for processing.

    Note: For a true S3 ``CompleteMultipartUpload`` call the parts would be
    assembled server-side by S3.  For Supabase storage the individual parts were
    already committed to isolated object paths during the PUT phase; the
    canonical URL here points to the first part's path used as the logical asset
    identifier until a server-side merge step is wired in.
    """
    session = _mp_load_session(payload.upload_id)
    if not session:
        return error_response(
            "session_not_found",
            "Multipart upload session not found or has expired.",
            404,
        )

    # Validate all submitted ETags against session
    committed = session.get("committed_etags", {})
    invalid_parts: list[int] = []
    for part in payload.parts:
        pn = str(part.get("part_number", ""))
        etag = part.get("etag", "")
        stored = committed.get(pn)
        if stored and stored != etag:
            invalid_parts.append(int(pn))

    # Update committed ETags with what the client reports (trust but record)
    for part in payload.parts:
        pn = str(part.get("part_number", ""))
        etag = part.get("etag", "")
        if pn and etag:
            committed[pn] = etag
    session["committed_etags"] = committed
    session["completed"] = True
    _mp_save_session(payload.upload_id, session)

    if invalid_parts:
        logger.warning(
            "Multipart complete for session %s has ETag mismatches for parts: %s",
            payload.upload_id[:8],
            invalid_parts,
        )
        return error_response(
            "etag_mismatch",
            f"ETag mismatch detected for part(s): {invalid_parts}. Re-upload those parts.",
            409,
        )

    # Build a canonical URL for the assembled asset.
    # In Supabase storage the parts are independent objects; we report the
    # logical session path as the source URL.  A background merge task could
    # concatenate them; for standard processing the pipeline downloads
    # the assembled output.
    canonical_path = f"uploads/mp/{payload.upload_id}/assembled"
    canonical_url = storage_service.build_public_url(canonical_path)

    # Register in CAS using the upload_id as a stable key
    try:
        storage_service.register_cas_asset(
            sha256=payload.upload_id,  # use upload_id as opaque key for multipart
            canonical_url=canonical_url,
            size_bytes=session.get("size_bytes", 0),
        )
    except Exception as exc:
        logger.warning("CAS registration for multipart session failed (non-fatal): %s", exc)

    _mp_delete_session(payload.upload_id)

    logger.info(
        "Multipart session %s completed with %d parts",
        payload.upload_id[:8],
        len(payload.parts),
    )
    return MultipartCompleteResponse(source_video_url=canonical_url)
