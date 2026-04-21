"""File: workers/regenerate_clips.py
Purpose: Background task to regenerate clips with custom weights/instructions.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID
from pathlib import Path
import tempfile

from openai import APIConnectionError, APITimeoutError, RateLimitError

from core.config import settings
from db.repositories.jobs import append_regeneration_result, get_job, update_job
from services.caption_renderer import write_clip_srt
from services.clip_detector import (
    get_clip_detector_service,
    SCORE_WEIGHTS as DEFAULT_WEIGHTS,
)
from services.storage import storage_service
from services.video_processor import cut_clip, render_vertical_captioned_clip
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
)


@celery_app.task(bind=True, name="workers.regenerate_clips.regenerate_clips_task")
def regenerate_clips_task(
    self,
    job_id: str,
    regen_id: str,
    clip_count: int = 3,
    custom_weights: dict[str, float] | None = None,
    instructions: str | None = None,
) -> dict:
    """Re-run clip detection with custom parameters.
    
    Args:
        job_id: Job ID
        regen_id: Unique regeneration request ID
        clip_count: Number of clips to find
        custom_weights: Custom SCORE_WEIGHTS override
        instructions: Natural language instruction to append to prompt
    
    Returns:
        Regeneration result dict
    """
    logger.info(
        "[job=%s] Regeneration started: %s (count=%d, weights=%s, instructions=%s)",
        job_id,
        regen_id,
        clip_count,
        custom_weights,
        instructions,
    )

    job = get_job(job_id)
    if not job:
        logger.error("[job=%s] Job not found", job_id)
        raise ValueError(f"Job {job_id} not found")

    if not job.transcript_json:
        logger.error("[job=%s] No transcript available for regeneration", job_id)
        raise ValueError(f"Job {job_id} has no transcript")

    temp_dir = Path(tempfile.mkdtemp(prefix=f"regen_{job_id}_"))

    try:
        # Get clip detector service
        clip_detector_service = get_clip_detector_service()

        # Merge weights (custom overrides default)
        weights = {**DEFAULT_WEIGHTS, **(custom_weights or {})}

        # Validate weights sum to 1.0
        total = sum(weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {total}")

        logger.debug("[regen=%s] Using weights: %s", regen_id, weights)

        # Re-detect clips with custom parameters
        detected_clips, llm_cost = clip_detector_service.detect_clips(
            transcript_json=job.transcript_json,
            custom_score_weights=weights,
            custom_prompt_instruction=instructions,
            limit=clip_count,
        )

        logger.info(
            "[regen=%s] Detection complete: %d clips found",
            regen_id,
            len(detected_clips),
        )

        # Build response
        result = {
            "regen_id": regen_id,
            "requested_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "weights": weights,
            "instructions": instructions,
            "clips": [c.model_dump() if hasattr(c, "model_dump") else dict(c) for c in detected_clips],
            "status": "completed",
            "error": None,
        }

        # Append to timeline
        append_regeneration_result(job_id, result)

        logger.info("[regen=%s] Results persisted to job timeline", regen_id)

        return result

    except TRANSIENT_ERRORS as exc:
        logger.error(
            "[regen=%s] Transient error during regeneration: %s",
            regen_id,
            exc,
            exc_info=True,
        )
        # Retry this task
        raise self.retry(exc=exc, countdown=5)

    except Exception as exc:
        logger.error(
            "[regen=%s] Regeneration failed: %s",
            regen_id,
            exc,
            exc_info=True,
        )

        # Save error result
        result = {
            "regen_id": regen_id,
            "requested_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "weights": custom_weights or {},
            "instructions": instructions,
            "clips": [],
            "status": "failed",
            "error": str(exc),
        }

        append_regeneration_result(job_id, result)
        return result

    finally:
        # Clean up temp directory
        import shutil

        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.debug("[regen=%s] Temp directory cleaned", regen_id)
        except Exception as exc:
            logger.warning("[regen=%s] Failed to clean temp dir: %s", regen_id, exc)
