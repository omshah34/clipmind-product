"""File: api/routes/hooks.py
Purpose: Hook Laboratory endpoints for A/B testing headline variants.
"""

from __future__ import annotations

import logging
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends

from api.dependencies import get_current_user, AuthenticatedUser
from api.dependencies.workspace import require_workspace_role
from db.repositories.jobs import get_job
from api.models.job import ErrorResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["hook-lab"])


@router.get("/{job_id}/clips/{clip_index}/hooks")
async def get_hook_variants(
    job_id: str, 
    clip_index: int,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Returns 3 AI-generated Hook variations (different start timestamps) for a specific clip."""
    from services.llm_integration import generate_hook_variants
    
    job = get_job(job_id)
    if not job or not job.clips_json:
        raise HTTPException(status_code=404, detail="Job or clips not found")
        
    if clip_index < 0 or clip_index >= len(job.clips_json):
        raise HTTPException(
            status_code=404, 
            detail=f"Clip index {clip_index} out of range"
        )
        
    hooks = generate_hook_variants(str(job_id), clip_index)
    variants = hooks if isinstance(hooks, list) else []
    
    return {
        "job_id": job_id,
        "clip_index": clip_index,
        "hooks": variants,
        "variants": variants,
    }


@router.post("/{job_id}/clips/{clip_index}/hooks/render")
async def render_hook_preview(
    job_id: str, 
    clip_index: int, 
    headline: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Triggers a 'Fast Preview' render (first 3-5s) of the clip with a custom headline overlay.
    """
    from workers.render_clips import render_hook_preview as render_task
    
    # Validate job exists
    job = get_job(job_id)
    if not job or not job.clips_json:
        raise HTTPException(status_code=404, detail="Job or clips not found")
        
    if clip_index < 0 or clip_index >= len(job.clips_json):
        raise HTTPException(status_code=400, detail="Invalid clip index")

    # Dispatch to Celery
    task = render_task.delay(
        job_id=str(job_id),
        clip_index=clip_index,
        headline=headline,
        user_id=str(user.user_id)
    )
    
    return {
        "status": "queued",
        "task_id": task.id,
        "message": "Hook preview render queued."
    }
