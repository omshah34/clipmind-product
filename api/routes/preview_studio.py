"""File: api/routes/preview_studio.py
Purpose: Preview studio endpoints for in-browser caption editing and render tracking.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from api.dependencies import AuthenticatedUser, get_current_user
from api.models.preview_studio import PreviewData, RenderRequest, RenderStatusResponse
from api.response_utils import normalize_model
from db.repositories.clip_sequences import get_job
from db.repositories.render_jobs import create_render_job, get_render_job
from services.caption_renderer import write_clip_srt, flatten_words
from services.render_recipe import merge_render_recipe
from services.task_queue import dispatch_task
from workers.render_clips import render_edited_clip

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/preview", tags=["preview_studio"])


def _clip_or_404(job_id: str, clip_index: int) -> tuple[Any, Any]:
    job = get_job(job_id)
    if not job or not job.clips_json:
        raise HTTPException(status_code=404, detail="Job or clips not found")
    if clip_index < 0 or clip_index >= len(job.clips_json):
        raise HTTPException(status_code=404, detail="Clip not found")
    return job, job.clips_json[clip_index]


def _clip_transcript_words(transcript_json: dict | None, start_time: float, end_time: float) -> list[dict]:
    words = flatten_words(transcript_json)
    return [
        {
            "word": str(word.get("word", "")),
            "start": float(word.get("start", 0)),
            "end": float(word.get("end", 0)),
        }
        for word in words
        if start_time <= float(word.get("start", 0)) <= end_time
    ]


def _build_preview_payload(job_id: str, clip_index: int) -> dict[str, Any]:
    job, clip = _clip_or_404(job_id, clip_index)

    start_time = float(getattr(clip, "start_time", 0))
    end_time = float(getattr(clip, "end_time", 0))
    transcript_words = _clip_transcript_words(getattr(job, "transcript_json", None), start_time, end_time)

    with tempfile.TemporaryDirectory() as tmpdir:
        srt_path = Path(tmpdir) / "preview.srt"
        if getattr(job, "transcript_json", None):
            write_clip_srt(job.transcript_json, start_time, end_time, srt_path)
            current_srt = srt_path.read_text(encoding="utf-8-sig")
        else:
            current_srt = "1\n00:00:00,000 --> 00:00:03,000\n[No Captions Found]\n"

    stream_url = f"/api/v1/jobs/{job_id}/clips/{clip_index}/stream"
    download_url = f"/api/v1/jobs/{job_id}/clips/{clip_index}/download"

    return {
        "job_id": str(job.id),
        "clip_index": clip_index,
        "status": str(job.status),
        "start_time": start_time,
        "end_time": end_time,
        "duration_seconds": end_time - start_time,
        "transcript_words": transcript_words,
        "current_srt": current_srt,
        "clip_url": stream_url,
        "download_url": download_url,
        "srt_url": getattr(clip, "srt_url", None),
        "layout_type": getattr(clip, "layout_type", None),
        "visual_mode": getattr(clip, "visual_mode", None),
        "selected_hook": getattr(clip, "selected_hook", None),
        "render_recipe": getattr(clip, "render_recipe", None),
    }


@router.get("/")
def list_previews() -> dict:
    return {"previews": []}


@router.get("/{job_id}/{clip_index}")
def get_preview(job_id: str, clip_index: int, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if str(job.user_id) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")
    return normalize_model(PreviewData, _build_preview_payload(job_id, clip_index))


@router.post("/{job_id}/{clip_index}/render", status_code=202)
def create_preview_render(
    job_id: str,
    clip_index: int,
    payload: RenderRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict[str, Any]:
    job, clip = _clip_or_404(job_id, clip_index)
    if str(job.user_id) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")

    edited_srt = payload.edited_srt
    if not edited_srt:
        raise HTTPException(status_code=400, detail="edited_srt is required")

    caption_style = payload.caption_style or {}
    render_recipe = merge_render_recipe(
        getattr(clip, "render_recipe", None),
        {
            "layout_type": payload.layout_type,
            "hook_text": payload.hook_text,
            "screen_focus": payload.screen_focus,
            "caption_preset": payload.caption_preset,
            "caption_enabled": payload.caption_enabled,
        },
    )
    render_job = create_render_job(
        user_id=user.user_id,
        job_id=job_id,
        clip_index=clip_index,
        edited_srt=edited_srt,
        caption_style=caption_style,
        render_recipe=render_recipe,
    )
    if not render_job:
        raise HTTPException(status_code=500, detail="Failed to create render job")

    dispatch_task(
        render_edited_clip,
        render_job["id"],
        job_id,
        clip_index,
        edited_srt,
        caption_style,
        fallback=lambda *task_args: render_edited_clip.apply(args=task_args, throw=True),
        task_name="workers.render_clips.render_edited_clip",
    )

    return normalize_model(RenderStatusResponse, {
        "render_job_id": str(render_job["id"]),
        "status": "queued",
        "progress_percent": 0,
        "created_at": render_job.get("created_at"),
        "output_url": None,
        "error_message": None,
        "completed_at": None,
    })


@router.get("/render-jobs/{render_job_id}")
def get_render_status(render_job_id: str, user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, Any]:
    render_job = get_render_job(render_job_id)
    if not render_job:
        raise HTTPException(status_code=404, detail="Render job not found")
    if str(render_job.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")

    return normalize_model(RenderStatusResponse, {
        "render_job_id": str(render_job.get("id")),
        "status": render_job.get("status"),
        "progress_percent": render_job.get("progress_percent"),
        "output_url": render_job.get("output_url"),
        "error_message": render_job.get("error_message"),
        "completed_at": render_job.get("completed_at"),
        "created_at": render_job.get("created_at"),
    })


@router.websocket("/render-jobs/{render_job_id}/ws")
async def render_status_ws(websocket: WebSocket, render_job_id: str) -> None:
    await websocket.accept()
    logger.info("[preview-ws] Render client connected for job=%s", render_job_id)

    last_payload: dict[str, Any] | None = None

    try:
        while True:
            render_job = await asyncio.to_thread(get_render_job, render_job_id)
            if not render_job:
                await websocket.send_json({"type": "error", "message": "Render job not found"})
                await websocket.close(code=1008, reason="Render job not found")
                return

            payload = normalize_model(RenderStatusResponse, {
                "render_job_id": str(render_job.get("id")),
                "status": render_job.get("status"),
                "progress_percent": render_job.get("progress_percent"),
                "output_url": render_job.get("output_url"),
                "error_message": render_job.get("error_message"),
                "completed_at": render_job.get("completed_at"),
                "created_at": render_job.get("created_at"),
            })
            if payload != last_payload:
                await websocket.send_json(payload)
                last_payload = payload

            if render_job.get("status") in {"completed", "failed"}:
                await asyncio.sleep(0.25)
                await websocket.close(code=1000, reason="Render complete")
                return

            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        logger.info("[preview-ws] Client disconnected for render job=%s", render_job_id)
