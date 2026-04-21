"""File: workers/render_clips.py
Purpose: FFmpeg rendering tasks for preview studio caption editing.
         Renders edited captions and styling into video files.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from uuid import UUID

from workers.celery_app import celery_app
from db.repositories.render_jobs import (
    get_render_job,
    update_render_job_status,
)
from services.storage import storage_service


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=3)
def render_edited_clip(
    self,
    render_job_id: str | UUID,
    job_id: str | UUID,
    clip_index: int,
    edited_srt: str,
    caption_style: dict | None = None,
) -> dict:
    """Render video clip with edited captions and styling.
    
    Args:
        render_job_id: Render job UUID
        job_id: Parent job UUID
        clip_index: Clip index in job
        edited_srt: Edited SRT content from preview studio
        caption_style: Caption styling (font, size, color, etc)
    
    Returns:
        Render job result with output URL
    """
    render_job_id = UUID(render_job_id) if isinstance(render_job_id, str) else render_job_id
    job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    
    try:
        # Update status to processing
        update_render_job_status(
            render_job_id,
            status="processing",
            progress_percent=10,
        )
        
        logger.info(f"Starting render for job {job_id} clip {clip_index}")
        
        # Get render job details from database
        render_job = get_render_job(render_job_id)
        if not render_job:
            logger.error(f"Render job {render_job_id} not found")
            update_render_job_status(
                render_job_id,
                status="failed",
                error_message="Render job not found",
            )
            return {"status": "failed", "error": "Render job not found"}
        
        # Get original clip video (from job storage)
        original_video_url = render_job.get("original_video_url")
        if not original_video_url:
            logger.error(f"No original video found for job {job_id}")
            update_render_job_status(
                render_job_id,
                status="failed",
                error_message="Original video not found",
            )
            return {"status": "failed", "error": "Original video not found"}
        
        # Create temporary files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            
            # Write edited SRT to temp file
            srt_file = tmpdir / "edited_captions.srt"
            srt_file.write_text(edited_srt, encoding="utf-8")
            
            # Get caption style with defaults
            style = caption_style or {}
            font_name = style.get("font", "Arial")
            font_size = style.get("size", 24)
            font_color = style.get("color", "white")
            bg_color = style.get("background", "black")
            
            # Use existing caption renderer with edited SRT
            rendered_video = tmpdir / "rendered_video.mp4"
            
            try:
                # Render captions onto video
                subtitle_file = tmpdir / "subtitle.srt"
                subtitle_file.write_text(edited_srt, encoding="utf-8")
                
                # FFmpeg command to add captions
                ffmpeg_cmd = [
                    "ffmpeg",
                    "-i", str(original_video_url),
                    "-vf", f"subtitles={subtitle_file}:force_style='FontName={font_name},FontSize={font_size},PrimaryColour=&H{font_color}&,OutlineColour=&H{bg_color}&'",
                    "-c:a", "aac",
                    "-y",
                    str(rendered_video),
                ]
                
                result = subprocess.run(
                    ffmpeg_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                
                if result.returncode != 0:
                    logger.error(f"FFmpeg failed: {result.stderr}")
                    update_render_job_status(
                        render_job_id,
                        status="failed",
                        error_message=f"FFmpeg error: {result.stderr[:200]}",
                    )
                    return {"status": "failed", "error": "FFmpeg rendering failed"}
                
                # Update progress
                update_render_job_status(
                    render_job_id,
                    status="processing",
                    progress_percent=70,
                )
                
                # Upload rendered video to storage
                user_id = render_job.get("user_id") or "anonymous"
                # suffix removed as it was undefined in previous view, likely local var in original file
                # fixing definedness
                filename = f"clip_{clip_index}.mp4" 
                output_url = storage_service.upload_file(
                    local_path=rendered_video,
                    folder=f"renders/{user_id}/{job_id}",
                    filename=filename,
                )
                
                # Mark complete
                update_render_job_status(
                    render_job_id,
                    status="completed",
                    output_url=output_url,
                    progress_percent=100,
                )
                
                logger.info(f"Render completed: {output_url}")
                
                return {
                    "status": "completed",
                    "render_job_id": str(render_job_id),
                    "output_url": output_url,
                }
            
            except subprocess.TimeoutExpired:
                logger.error(f"FFmpeg timeout for render {render_job_id}")
                update_render_job_status(
                    render_job_id,
                    status="failed",
                    error_message="Rendering timeout (>5 min)",
                )
                return {"status": "failed", "error": "FFmpeg timeout"}
    
    except Exception as exc:
        logger.exception(f"Render task failed: {exc}")
        
        # Retry with exponential backoff
        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except Exception:
            # If not a retry exception, return failed
            return {"status": "failed", "error": str(exc)}

@celery_app.task(bind=True, max_retries=2)
def render_hook_preview(
    self,
    job_id: str | UUID,
    clip_index: int,
    headline: str,
    user_id: str | None = None,
) -> dict:
    """Render a 3-second 'Fast Preview' of a clip with a headline overlay.
    
    Args:
        job_id: Parent job UUID
        clip_index: Clip index
        headline: Text to overlay
        user_id: For storage pathing
    """
    job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    from db.repositories.jobs import get_job
    
    job = get_job(job_id)
    if not job:
        return {"status": "failed", "error": "Job not found"}
        
    source_video = job.source_video_url  # URL or path
    
    # Get clip start time
    if not job.clips_json or clip_index >= len(job.clips_json):
        return {"status": "failed", "error": "Clip index out of range"}
    
    clip_start = job.clips_json[clip_index].start_time
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            output_file = tmpdir_path / f"hook_preview_{clip_index}.mp4"
            
            # FFmpeg Command for Hook Preview:
            # 1. Start at clip_start
            # 2. Duration 3 seconds
            # 3. Vertical Crop (center 9:16)
            # 4. Scale to 720p height (Fast Preview)
            # 5. DrawText headline
            
            # Simple box + text for maximum legibility
            safe_headline = headline.replace("'", "").replace(":", "")
            drawtext_filter = (
                f"drawtext=text='{safe_headline}':fontcolor=white:fontsize=48:"
                f"box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h/4"
            )
            
            # Assuming landscape input, center crop to 9:16 aspect
            vf_filter = (
                f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=-1:720,{drawtext_filter}"
            )
            
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-ss", str(clip_start),
                "-i", str(source_video),
                "-t", "3",
                "-vf", vf_filter,
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "28",
                "-c:a", "aac",
                str(output_file)
            ]
            
            logger.info(f"Rendering hook preview: {' '.join(ffmpeg_cmd)}")
            
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                logger.error(f"Hook render failed: {result.stderr}")
                return {"status": "failed", "error": result.stderr}
                
            # Upload
            user_id_str = user_id or "anonymous"
            output_url = storage_service.upload_file(
                local_path=output_file,
                folder=f"previews/{user_id_str}/{job_id}",
                filename=f"hook_{clip_index}_{abs(hash(headline)) % 1000}.mp4"
            )
            
            return {
                "status": "completed",
                "preview_url": output_url,
                "headline": headline
            }
            
    except Exception as exc:
        logger.exception(f"Hook preview failed: {exc}")
        return {"status": "failed", "error": str(exc)}
