# File: api/routes/clip_studio.py
# Purpose: Clip Studio endpoints for timeline editing, regeneration, and preview.
#          - GET  /jobs/{id}/preview                     : Lightweight metadata
#          - GET  /jobs/{id}/clips/{index}/stream        : Stream video (range-aware)
#          - GET  /jobs/{id}/clips/{index}/download      : Force-download video
#          - POST /jobs/{id}/regenerate                  : Re-run detection with custom weights
#          - PATCH /jobs/{id}/clips/{index}/adjust       : Adjust clip boundaries

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from urllib.parse import urlparse, unquote
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text
from api.dependencies import get_current_user, AuthenticatedUser

from api.models.clip_studio import (
    AdjustClipBoundaryRequest,
    AdjustClipBoundaryResponse,
    ClipPreviewData,
    RegenerationRequest,
    RegenerateClipsResponse,
)
from api.models.job import ErrorResponse
from db.repositories.clip_sequences import (
    append_regeneration_result,
    get_job,
    get_job_timeline,
    update_job,
    update_job_timeline,
)
from db.repositories.jobs import normalize_clip_indices
from db.repositories.render_jobs import create_render_job
from services.storage import storage_service
from services.task_queue import dispatch_task
from services.content_dna import record_signal
from services.caption_renderer import write_clip_srt
from services.render_recipe import merge_render_recipe
from workers.render_clips import render_edited_clip
from workers.regenerate_clips import regenerate_clips_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["clip-studio"])

# ── Helpers ──────────────────────────────────────────────────────────────────

def error_response(error: str, message: str, status_code: int) -> JSONResponse:
    payload = ErrorResponse(error=error, message=message)
    return JSONResponse(status_code=status_code, content=payload.model_dump())

def _resolve_clip_url(raw_url: str | None) -> str | None:
    """Convert stored clip_url (S3 URI / local path / HTTP URL) to a
    publicly accessible HTTP URL using the storage service.

    Returns None when the URL cannot be resolved.
    """
    if not raw_url or raw_url in ("None", ""):
        return None

    # Already a public HTTP(S) URL — use as-is (may be a presigned URL).
    if raw_url.startswith(("http://", "https://")):
        return raw_url

    # S3 URI — ask the storage service for a presigned URL.
    if raw_url.startswith("s3://"):
        try:
            return storage_service.get_presigned_url(raw_url, expires_in=3600)
        except Exception:
            logger.warning("Could not generate presigned URL for %s", raw_url)
            return None

    # Local filesystem path — will be served by our stream endpoint later.
    # Return None so the caller knows to substitute the /stream route.
    if os.path.exists(raw_url):
        return None  # caller replaces with /stream route

    logger.warning("Unrecognised clip_url format: %s", raw_url)
    return None


def _get_clip_record(job_id: str, clip_index: int):
    """Return the raw clip record or raise 404."""
    job = get_job(job_id)
    if not job or not job.clips_json:
        raise HTTPException(status_code=404, detail="Job or clips not found")
    if clip_index < 0 or clip_index >= len(job.clips_json):
        raise HTTPException(
            status_code=404,
            detail=f"Clip index {clip_index} out of range (0-{len(job.clips_json) - 1})",
        )
    return job.clips_json[clip_index]


# ── Stream / Download ─────────────────────────────────────────────────────────

@router.get("/{job_id}/clips/{clip_index}/stream")
async def stream_clip(job_id: str, clip_index: int, request: Request):
    """Stream a clip video with HTTP range support so the browser
    can seek and the <video> element works correctly.

    Resolution priority:
      1. file:// URI           → resolve to local path, stream from disk
      2. HTTPS presigned URL   → proxy with range forwarding
      3. S3 URI                → resolve to presigned URL then proxy
      4. Raw local file path   → stream from disk
    """
    clip = _get_clip_record(job_id, clip_index)
    raw_url: str = str(clip.clip_url)

    logger.debug("[stream] job=%s clip=%d raw_url=%s", job_id, clip_index, raw_url)

    # ── Case 1: file:// URI (local storage on dev) ────────────────────────
    #    StorageService.upload_file returns file:///C:/... on Windows when
    #    Supabase is not configured.
    if raw_url.startswith("file://"):
        parsed = urlparse(raw_url)
        # On Windows urlparse gives path like /C:/..., strip leading slash
        decoded = unquote(parsed.path)
        if decoded.startswith("/") and len(decoded) > 2 and decoded[2] == ":":
            decoded = decoded[1:]  # "/C:/foo" → "C:/foo"
        raw_url = decoded  # fall through to local-file handler below
        logger.debug("[stream] Resolved file:// URI to: %s", raw_url)

    # ── Case 2: HTTP URL (presigned or public) ────────────────────────────
    if raw_url.startswith(("http://", "https://")):
        # Forward the client's Range header so seeking works.
        upstream_headers = {}
        if "range" in request.headers:
            upstream_headers["Range"] = request.headers["range"]

        async def _proxy():
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream("GET", raw_url, headers=upstream_headers) as r:
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        yield chunk

        # Probe for content-length / accept-ranges from upstream.
        try:
            head = httpx.head(raw_url, timeout=10)
            proxy_headers = {
                "Content-Type": head.headers.get("content-type", "video/mp4"),
                "Accept-Ranges": "bytes",
            }
            if "content-length" in head.headers:
                proxy_headers["Content-Length"] = head.headers["content-length"]
            status = 206 if "range" in request.headers else 200
        except Exception:
            proxy_headers = {"Content-Type": "video/mp4", "Accept-Ranges": "bytes"}
            status = 200

        return StreamingResponse(_proxy(), status_code=status, headers=proxy_headers)

    # ── Case 3: S3 URI → resolve to presigned URL then proxy ─────────────
    if raw_url.startswith("s3://"):
        try:
            presigned = storage_service.get_presigned_url(raw_url, expires_in=3600)
            upstream_headers = {}
            if "range" in request.headers:
                upstream_headers["Range"] = request.headers["range"]

            async def _s3_proxy():
                async with httpx.AsyncClient(timeout=60) as client:
                    async with client.stream("GET", presigned, headers=upstream_headers) as r:
                        async for chunk in r.aiter_bytes(chunk_size=65536):
                            yield chunk

            head = httpx.head(presigned, timeout=10)
            proxy_headers = {
                "Content-Type": head.headers.get("content-type", "video/mp4"),
                "Accept-Ranges": "bytes",
            }
            if "content-length" in head.headers:
                proxy_headers["Content-Length"] = head.headers["content-length"]
            status = 206 if "range" in request.headers else 200
            return StreamingResponse(_s3_proxy(), status_code=status, headers=proxy_headers)
        except Exception as exc:
            logger.error("S3 stream failed for %s: %s", raw_url, exc)
            raise HTTPException(status_code=502, detail="Could not retrieve clip from storage")

    # ── Case 4: Local file path ───────────────────────────────────────────
    file_path = Path(raw_url)
    if not file_path.exists():
        logger.error("[stream] Clip file NOT found: %s", file_path)
        raise HTTPException(status_code=404, detail=f"Clip file not found on disk: {file_path}")

    file_size = file_path.stat().st_size
    content_type = mimetypes.guess_type(str(file_path))[0] or "video/mp4"
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            range_val = range_header.replace("bytes=", "")
            start_str, end_str = range_val.split("-")
            start = int(start_str)
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def _local_range():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            _local_range(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": content_type,
            },
        )

    def _local_full():
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                yield chunk

    return StreamingResponse(
        _local_full(),
        status_code=200,
        headers={
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
            "Content-Type": content_type,
        },
    )


@router.get("/{job_id}/clips/{clip_index}/download")
async def download_clip(
    job_id: str, 
    clip_index: int, 
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Same as /stream but forces a browser download via Content-Disposition."""
    # Reuse the streaming logic by delegating to stream_clip,
    # then wrap the response with attachment headers.
    streaming = await stream_clip(job_id, clip_index, request)
    streaming.headers["Content-Disposition"] = (
        f'attachment; filename="clipmind-clip-{clip_index + 1}.mp4"'
    )
    
    # ── Content DNA Signal ───────────────────────────────────────────────
    # We record this as a strong positive signal.
    # Note: In a production app, we'd get the user_id from the auth token.
    record_signal(
        user_id=user.user_id,
        job_id=str(job_id),
        clip_index=clip_index,
        signal_type="download"
    )

    return streaming


# ── Preview ───────────────────────────────────────────────────────────────────

@router.get("/{job_id}/preview", status_code=200)
def get_job_preview(job_id: str) -> ClipPreviewData:
    """Get lightweight preview data for timeline editor (no FFmpeg render).

    clip_url in the response always points to the /stream API endpoint so
    the browser can play and seek without CORS or S3 URI issues.
    """
    job = get_job(job_id)
    if not job:
        return error_response("job_not_found", "Job not found", 404)

    if job.status != "completed" or job.clips_json is None or job.transcript_json is None:
        return error_response(
            "job_not_ready",
            f"Job must be completed. Current status: {job.status}",
            409,
        )

    # Transcript words
    transcript_words = []
    if job.transcript_json and isinstance(job.transcript_json, dict):
        for segment in job.transcript_json.get("segments", []):
            for word_obj in segment.get("words", []):
                transcript_words.append({
                    "word": word_obj.get("word", ""),
                    "start": float(word_obj.get("start", 0)),
                    "end": float(word_obj.get("end", 0)),
                })

    # Build clips — always use the /stream API route as clip_url so the
    # frontend gets a guaranteed HTTP URL that supports range requests.
    current_clips = []
    for i, clip in enumerate(job.clips_json):
        raw_url = str(clip.clip_url)
        has_clip = raw_url not in ("", "None", None) and raw_url != "None"

        # Use our proxy endpoint as the canonical URL. This works regardless
        # of whether the underlying file is on S3, local disk, or a CDN.
        stream_url = f"/api/v1/jobs/{job_id}/clips/{i}/stream" if has_clip else ""

        current_clips.append({
            "clip_index": i,
            "start_time": float(clip.start_time),
            "end_time": float(clip.end_time),
            "duration": float(clip.duration),
            "hook_score": float(clip.hook_score),
            "emotion_score": float(clip.emotion_score),
            "clarity_score": float(clip.clarity_score),
            "story_score": float(clip.story_score),
            "virality_score": float(clip.virality_score),
            "final_score": float(clip.final_score),
            "score_source": getattr(clip, "score_source", "llm"),
            "score_confidence": float(getattr(clip, "score_confidence", 1.0)),
            "reason": str(clip.reason),
            "clip_url": stream_url,          # ← always an HTTP URL now
            "download_url": f"/api/v1/jobs/{job_id}/clips/{i}/download" if has_clip else "",
            "srt_url": getattr(clip, "srt_url", None),
            "layout_type": getattr(clip, "layout_type", None),
            "visual_mode": getattr(clip, "visual_mode", None),
            "selected_hook": getattr(clip, "selected_hook", None),
            "render_recipe": getattr(clip, "render_recipe", None),
        })

    timeline = get_job_timeline(job_id)
    regen_count = len(timeline.get("regeneration_results", [])) if timeline else 0

    return ClipPreviewData(
        job_id=job.id,
        status=job.status,
        transcript_words=transcript_words,
        current_clips=current_clips,
        regeneration_count=regen_count,
    )


# ── Regenerate ────────────────────────────────────────────────────────────────

@router.post("/{job_id}/regenerate", status_code=202)
def regenerate_clips(
    job_id: str,
    payload: RegenerationRequest = RegenerationRequest(),
    user: AuthenticatedUser = Depends(get_current_user)
) -> RegenerateClipsResponse:
    """Queue a background task to regenerate clips with custom parameters."""
    job = get_job(job_id)
    if not job:
        return error_response("job_not_found", "Job not found", 404)

    if not job.transcript_json:
        return error_response(
            "job_not_ready",
            "Job must have transcript before regeneration",
            409,
        )

    if payload.custom_weights:
        total_weight = sum(payload.custom_weights.values())
        if abs(total_weight - 1.0) > 0.01:
            return error_response(
                "invalid_weights",
                f"Weights must sum to 1.0, got {total_weight:.2f}",
                400,
            )

    regen_id = str(uuid4())
    logger.info(
        "[job=%s] Regeneration request created: %s (count=%d, weights=%s, instructions=%s)",
        job_id, regen_id, payload.clip_count, payload.custom_weights, payload.instructions,
    )

    dispatch_task(
        regenerate_clips_task,
        str(job_id),
        regen_id,
        payload.clip_count,
        payload.custom_weights,
        payload.instructions,
        fallback=lambda *task_args: regenerate_clips_task.apply(args=task_args, throw=True),
        task_name="workers.regenerate_clips.regenerate_clips_task",
    )

    # ── Content DNA Signal ───────────────────────────────────────────────
    # Regenerate is a weak negative signal (the first set of clips didn't satisfy)
    record_signal(
        user_id=user.user_id,
        job_id=str(job_id),
        clip_index=0, # Job-level signal
        signal_type="regenerate",
        metadata={"instructions": payload.instructions}
    )

    return RegenerateClipsResponse(
        regen_id=regen_id,
        status="queued",
        message=f"Regeneration {regen_id} queued. Poll /jobs/{job_id}/status for results.",
    )


# ── Adjust boundary ───────────────────────────────────────────────────────────

@router.patch("/{job_id}/clips/{clip_index}/adjust", status_code=200)
def adjust_clip_boundary(
    job_id: str,
    clip_index: int,
    payload: AdjustClipBoundaryRequest,
    background_tasks: BackgroundTasks,
    user: AuthenticatedUser = Depends(get_current_user)
) -> AdjustClipBoundaryResponse:
    """Adjust a clip's start/end times based on the Context-Bound Transcript Handle UI."""
    job = get_job(job_id)
    if not job or not job.clips_json:
        return error_response("job_not_found", "Job or clips not found", 404)

    if clip_index < 0 or clip_index >= len(job.clips_json):
        return error_response(
            "invalid_clip_index",
            f"Clip index {clip_index} out of range (0-{len(job.clips_json) - 1})",
            400,
        )

    if payload.new_start < 0:
        return error_response("invalid_boundary", "Start time cannot be negative", 400)

    duration = payload.new_end - payload.new_start
    if duration < 3.0:
        return error_response("clip_too_short", "Clip must be at least 3 seconds", 400)

    old_clip = job.clips_json[clip_index]
    logger.info(
        "[job=%s] Clip %d adjustment: %.1fs-%.1fs → %.1fs-%.1fs",
        job_id, clip_index,
        getattr(old_clip, 'start_time', 0), getattr(old_clip, 'end_time', 0),
        payload.new_start, payload.new_end,
    )

    # 1. Update the actual clips_json so it saves immediately
    clips = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in job.clips_json]
    clips[clip_index]["start_time"] = payload.new_start
    clips[clip_index]["end_time"] = payload.new_end
    clips[clip_index]["duration"] = duration
    update_job(job_id, clips_json=clips)

    # 2. Update timeline logging
    timeline = get_job_timeline(job_id) or {"clips": [], "regeneration_results": []}
    timeline.setdefault("clips", []).append({
        "index": clip_index,
        "original_start": getattr(old_clip, 'start_time', 0),
        "original_end": getattr(old_clip, 'end_time', 0),
        "user_start": payload.new_start,
        "user_end": payload.new_end,
    })
    update_job_timeline(job_id, timeline)

    def _queue_rerender() -> None:
        try:
            latest_job = get_job(job_id)
            if not latest_job or not getattr(latest_job, "transcript_json", None):
                logger.warning("[job=%s] Skipping rerender: transcript not available", job_id)
                return

            with tempfile.TemporaryDirectory() as tmpdir:
                tmpdir_path = Path(tmpdir)
                srt_path = tmpdir_path / "edited_captions.srt"
                write_clip_srt(latest_job.transcript_json, payload.new_start, payload.new_end, srt_path)
                edited_srt = srt_path.read_text(encoding="utf-8")

            render_job = create_render_job(
                user_id=user.user_id,
                job_id=job_id,
                clip_index=clip_index,
                edited_srt=edited_srt,
                caption_style=None,
                render_recipe=merge_render_recipe(getattr(old_clip, "render_recipe", None)),
            )
            if not render_job:
                logger.error("[job=%s] Failed to create render job for clip %d", job_id, clip_index)
                return

            dispatch_task(
                render_edited_clip,
                render_job["id"],
                job_id,
                clip_index,
                edited_srt,
                None,
                fallback=lambda *task_args: render_edited_clip.apply(args=task_args, throw=True),
                task_name="workers.render_clips.render_edited_clip",
            )
        except Exception:
            logger.exception("[job=%s] Rerender queue failed for clip %d", job_id, clip_index)

    background_tasks.add_task(_queue_rerender)

    new_clip_url = f"/api/v1/jobs/{job_id}/clips/{clip_index}/stream"

    # ── Content DNA Signal ───────────────────────────────────────────────
    # Adjusting a clip is a positive signal (the user cares enough to fix it)
    record_signal(
        user_id=user.user_id,
        job_id=str(job_id),
        clip_index=clip_index,
        signal_type="edit",
        metadata={"new_start": payload.new_start, "new_end": payload.new_end}
    )

    return AdjustClipBoundaryResponse(
        clip_index=clip_index,
        new_start=payload.new_start,
        new_end=payload.new_end,
        duration=duration,
        clip_url=new_clip_url,
        message="Clip boundary adjusted",
    )


@router.patch("/{job_id}/clips/{clip_index}/transcript", status_code=200)
async def update_transcript(
    job_id: str,
    clip_index: int,
    new_text: str = Query(..., min_length=1),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Gap 293: Update clip transcript and immediately refresh search index.
    """
    from db.connection import engine
    
    with engine.begin() as conn:
        # 1. Update the transcript
        conn.execute(
            text("UPDATE clips SET transcript_text = :text WHERE job_id = :job_id AND clip_index = :index"),
            {"text": new_text, "job_id": job_id, "index": clip_index}
        )

        # 2. Immediately refresh tsvector (Postgres)
        # COALESCE ensures it doesn't fail on NULL title
        conn.execute(text("""
            UPDATE clips
            SET search_vector = to_tsvector('english', COALESCE(transcript_text, '') || ' ' || COALESCE(title, ''))
            WHERE job_id = :job_id AND clip_index = :index
        """), {"job_id": job_id, "index": clip_index})

        # SQLite fallback — FTS5 table sync (if table exists)
        try:
            conn.execute(text("""
                INSERT INTO clips_fts(clips_fts, rowid, transcript_text, title)
                VALUES('delete', (SELECT rowid FROM clips WHERE job_id=:job_id AND clip_index=:index), '', '')
            """), {"job_id": job_id, "index": clip_index})
            
            conn.execute(text("""
                INSERT INTO clips_fts(rowid, transcript_text, title)
                SELECT rowid, transcript_text, title FROM clips
                WHERE job_id=:job_id AND clip_index=:index
            """), {"job_id": job_id, "index": clip_index})
        except Exception:
            # Table might not exist or not be SQLite
            pass

    return {"status": "success", "message": "Transcript updated and search index refreshed."}

# -- Regenerations list -------------------------------------------------------

@router.get("/{job_id}/regenerations", status_code=200)
def get_regenerations(
    job_id: str,
    limit: int = Query(10, ge=1, le=50),
) -> JSONResponse:
    """Get list of past regeneration requests for a job."""
    job = get_job(job_id)
    if not job:
        return error_response("job_not_found", "Job not found", 404)

    timeline = get_job_timeline(job_id)
    if not timeline:
        return JSONResponse(status_code=200, content={"regenerations": []})

    regenerations = timeline.get("regeneration_results", [])[:limit]
    return JSONResponse(status_code=200, content={"regenerations": regenerations})


@router.post("/{job_id}/clips/{clip_index}/approve", status_code=200)
def approve_clip(
    job_id: str,
    clip_index: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """(Feature 5) Approve a clip from the Swipe-to-Approve PWA."""
    job = get_job(job_id)
    if not job or not job.clips_json:
        return error_response("job_not_found", "Job not found", 404)

    clips = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in job.clips_json]
    if clip_index < 0 or clip_index >= len(clips):
        return error_response("invalid_clip", "Clip index out of range", 400)

    clips[clip_index]["user_status"] = "approved"
    update_job(job_id, clips_json=clips)

    logger.info("Clip %d for job %s APPROVED via PWA.", clip_index, job_id)
    return {"status": "success", "message": "Clip approved and queued for HD export."}


@router.post("/{job_id}/clips/{clip_index}/discard", status_code=200)
def discard_clip(
    job_id: str,
    clip_index: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """(Feature 5) Discard a clip from the Swipe-to-Approve PWA so it is hidden."""
    job = get_job(job_id)
    if not job or not job.clips_json:
        return error_response("job_not_found", "Job not found", 404)

    clips = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in job.clips_json]
    if clip_index < 0 or clip_index >= len(clips):
        return error_response("invalid_clip", "Clip index out of range", 400)

    clips[clip_index]["user_status"] = "discarded"
    update_job(job_id, clips_json=clips)

    logger.info("Clip %d for job %s DISCARDED via PWA.", clip_index, job_id)
    return {"status": "success", "message": "Clip discarded."}


@router.delete("/{job_id}/clips/{clip_index}", status_code=200)
def delete_clip(
    job_id: str,
    clip_index: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Permanently remove a clip from the job and re-sequence clip_index values.

    Gap 179: After removal the remaining clips are re-indexed so that deep
    links encoded as /jobs/{id}/clips/{clip_index}/stream always resolve to
    the correct clip regardless of which earlier clip was deleted.
    """
    job = get_job(job_id)
    if not job or not job.clips_json:
        return error_response("job_not_found", "Job not found", 404)

    clips = [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in job.clips_json]
    if clip_index < 0 or clip_index >= len(clips):
        return error_response("invalid_clip", "Clip index out of range", 400)

    removed = clips.pop(clip_index)
    update_job(job_id, clips_json=clips)

    # Gap 179: Re-sequence clip_index so remaining clips stay contiguous (0,1,2,...)
    normalize_clip_indices(job_id)

    logger.info(
        "Clip %d permanently deleted from job %s; indices normalised.",
        clip_index, job_id
    )
    return {
        "status": "success",
        "message": f"Clip {clip_index} deleted and indices re-sequenced.",
        "deleted_clip_url": removed.get("clip_url"),
        "remaining_clips": len(clips),
    }
