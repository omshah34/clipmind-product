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

from db.repositories.brand_kits import get_brand_kit
from db.repositories.jobs import get_job
from workers.celery_app import celery_app
from db.repositories.render_jobs import (
    get_render_job,
    update_render_job_status,
)
from services.brand_kit_renderer import brand_kit_to_subtitle_style
from services.caption_renderer import write_ass_from_srt
from services.render_recipe import merge_render_recipe
from services.storage import storage_service
from services.video_processor import (
    DEFAULT_SUBTITLE_STYLE,
    SubtitleStyle,
    cut_clip,
    render_vertical_captioned_clip,
)


logger = logging.getLogger(__name__)


def _hex_to_ass_colour(value: str | None, fallback: str) -> str:
    if not value:
        return fallback
    cleaned = str(value).strip().lstrip("#")
    if len(cleaned) != 6:
        return fallback
    rr = cleaned[0:2]
    gg = cleaned[2:4]
    bb = cleaned[4:6]
    return f"&H00{bb}{gg}{rr}"


def _subtitle_style_from_inputs(job, caption_style: dict | None) -> SubtitleStyle:
    base_style = DEFAULT_SUBTITLE_STYLE
    if getattr(job, "brand_kit_id", None):
        brand_kit = get_brand_kit(job.brand_kit_id)
        if brand_kit:
            base_style = brand_kit_to_subtitle_style(brand_kit)

    style = caption_style or {}
    return SubtitleStyle(
        font_name=str(style.get("font") or base_style.font_name),
        font_size=int(style.get("size") or base_style.font_size),
        bold=base_style.bold,
        alignment=base_style.alignment,
        primary_colour=_hex_to_ass_colour(style.get("color"), base_style.primary_colour),
        outline_colour=_hex_to_ass_colour(style.get("background"), base_style.outline_colour),
        outline=base_style.outline,
    )


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
        
        job = get_job(job_id)
        if not job or not job.clips_json:
            logger.error("Job %s or clips not found for rerender", job_id)
            update_render_job_status(
                render_job_id,
                status="failed",
                error_message="Job or clips not found",
            )
            return {"status": "failed", "error": "Job or clips not found"}

        if clip_index < 0 or clip_index >= len(job.clips_json):
            logger.error("Clip %s out of range for job %s", clip_index, job_id)
            update_render_job_status(
                render_job_id,
                status="failed",
                error_message="Clip index out of range",
            )
            return {"status": "failed", "error": "Clip index out of range"}

        clip = job.clips_json[clip_index]
        if not getattr(job, "source_video_url", None):
            logger.error("No source video found for job %s", job_id)
            update_render_job_status(
                render_job_id,
                status="failed",
                error_message="Source video not found",
            )
            return {"status": "failed", "error": "Source video not found"}

        # Create temporary files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            source_video = tmpdir / "source_video.mp4"
            raw_clip = tmpdir / f"clip_{clip_index}_raw.mp4"
            ass_file = tmpdir / "edited_captions.ass"
            rendered_video = tmpdir / "rendered_video.mp4"

            try:
                storage_service.download_to_local(job.source_video_url, source_video)
                cut_clip(
                    source_video,
                    start_time=float(getattr(clip, "start_time", 0)),
                    end_time=float(getattr(clip, "end_time", 0)),
                    output_path=raw_clip,
                )

                recipe = merge_render_recipe(
                    getattr(clip, "render_recipe", None),
                    render_job.get("render_recipe_json") or {},
                )
                write_ass_from_srt(
                    edited_srt,
                    ass_file,
                    preset_name=str(recipe.get("caption_preset") or "hormozi"),
                    layout_type=str(recipe.get("layout_type") or "vertical"),
                )

                # Update progress
                update_render_job_status(
                    render_job_id,
                    status="processing",
                    progress_percent=55,
                )

                subtitle_style = _subtitle_style_from_inputs(job, caption_style)
                watermark_path = None
                if getattr(job, "brand_kit_id", None):
                    brand_kit = get_brand_kit(job.brand_kit_id)
                    if brand_kit and getattr(brand_kit, "watermark_url", None):
                        watermark_path = tmpdir / f"watermark_{job.brand_kit_id}.png"
                        storage_service.download_to_local(brand_kit.watermark_url, watermark_path)

                render_vertical_captioned_clip(
                    raw_clip,
                    ass_file,
                    rendered_video,
                    style=subtitle_style,
                    subject_centers=list(recipe.get("subject_centers") or []),
                    layout_type=str(recipe.get("layout_type") or "vertical"),
                    watermark_path=watermark_path,
                    headline=str(recipe.get("selected_hook") or "").strip() or None,
                    screen_focus=str(recipe.get("screen_focus") or "center"),
                    audio_profile=str(recipe.get("audio_profile") or "loudnorm_i_-14"),
                    render_recipe=recipe,
                )

                update_render_job_status(
                    render_job_id,
                    status="processing",
                    progress_percent=80,
                )

                # Upload rendered video to storage
                user_id = render_job.get("user_id") or "anonymous"
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
                logger.exception("Rerender failed for job %s clip %s", job_id, clip_index)
                update_render_job_status(
                    render_job_id,
                    status="failed",
                    error_message=str(exc)[:400],
                )
                return {"status": "failed", "error": str(exc)}
    
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
