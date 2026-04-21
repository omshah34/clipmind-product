"""
File: api/routes/exports.py
Purpose: API endpoints for omnichannel content exports (LinkedIn, Newsletter).
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from api.dependencies import get_current_user, AuthenticatedUser
from services.export_engine import get_export_engine, ToneType
from services.batch_service import BatchService
from db.repositories.jobs import get_job

logger = logging.getLogger(__name__)
exports_router = APIRouter(prefix="/exports", tags=["exports"])

class LinkedInExportRequest(BaseModel):
    job_id: str
    clip_index: int
    tone: Optional[ToneType] = "professional"

class NewsletterExportRequest(BaseModel):
    job_id: str

@exports_router.post("/clip/linkedin")
async def export_linkedin_post(
    req: LinkedInExportRequest,
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """Generate a LinkedIn post for a specific clip in a job."""
    job = get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Ownership check
    if str(job.user_id) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")

    clips = job.get("clips_json", [])
    if not clips or req.clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip not found at specified index")

    clip = clips[req.clip_index]
    
    # Get transcript segment - this might require fetching the transcript_json
    # and slicing it by clip start/end. For now, we use the 'reason' and 'hook_headlines'
    # as context for the LLM if transcript slicing is complex.
    # Ideally, we want the transcript text.
    
    # Simple transcript extraction logic (from words)
    transcript_text = "See video for details."
    if job.get("transcript_json"):
        from services.caption_renderer import flatten_words
        words = flatten_words(job["transcript_json"])
        start = float(clip["start_time"])
        end = float(clip["end_time"])
        segment_words = [w["word"] for w in words if start <= float(w["start"]) <= end]
        transcript_text = " ".join(segment_words)

    engine = get_export_engine()
    content = await engine.generate_linkedin_post(
        transcript_segment=transcript_text,
        ai_reasoning=clip.get("reason", ""),
        tone=req.tone
    )
    
    return {
        "platform": "linkedin",
        "type": "text_post",
        "content": content,
        "clip_index": req.clip_index
    }

@exports_router.post("/job/newsletter")
async def export_newsletter_draft(
    req: NewsletterExportRequest,
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """Generate a cohesive newsletter draft for an entire job's output."""
    job = get_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if str(job.user_id) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")

    engine = get_export_engine()
    content = await engine.generate_newsletter_draft(req.job_id)
    
    return {
        "platform": "newsletter",
        "content": content,
        "format": "markdown"
    }

@exports_router.get("/clip/linkedin/carousel-pdf")
async def get_carousel_pdf_status(
    clip_index: int,
    job_id: str,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Specced endpoint for PDF generation."""
    engine = get_export_engine()
    return engine.generate_linkedin_carousel_pdf(f"{job_id}_{clip_index}")

@exports_router.get("/job/{job_id}/sync-bridge")
async def export_sync_bridge(
    job_id: str,
    format: Literal["premiere", "davinci"] = Query("premiere"),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Download a sequence file for professional NLE integration.
    - format=premiere (XMEML v5)
    - format=davinci (FCPXML v1.10)
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if str(job.user_id) != str(user.user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")

    engine = get_export_engine()
    xml_content = engine.generate_sync_bridge_xml(job_id, format=format)
    if not xml_content:
        raise HTTPException(status_code=400, detail="No clips available for this job to export")
    
    filename = f"clipmind_{job_id[:8]}_{format}.xml"
    media_type = "application/xml"
    
    return Response(
        content=xml_content, 
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@exports_router.get("/job/{job_id}/social-pulse")
async def get_social_pulse(
    job_id: str,
    clip_index: int = 0
):
    """Generate high-engagement social media package for a clip."""
    job = get_job(job_id)
    if not job or not job.clips_json or clip_index >= len(job.clips_json):
        raise HTTPException(status_code=404, detail="Clip not found")
        
    engine = get_export_engine()
    clip = job.clips_json[clip_index]
    pulse = await engine.generate_social_pulse(clip.model_dump())
    return pulse

@exports_router.get("/job/{job_id}/social-pulse/all")
async def get_all_social_pulses(
    job_id: str,
    # user: AuthenticatedUser = Depends(get_current_user)
):
    """Generate social media packages for all clips in a job (Agency Batch Mode)."""
    job = get_job(job_id)
    if not job or not job.clips_json:
        raise HTTPException(status_code=404, detail="Job or clips not found")
        
    engine = get_export_engine()
    pulses = []
    
    # We could parallelize this with asyncio.gather for speed
    import asyncio
    tasks = [engine.generate_social_pulse(clip.model_dump()) for clip in job.clips_json]
    pulses = await asyncio.gather(*tasks)
    
    return {
        "job_id": job_id,
        "clip_count": len(pulses),
        "pulses": pulses
    }

@exports_router.post("/batch/trigger")
async def trigger_batch_process(
    job_ids: list[str],
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Triggers background processing for a batch of jobs.
    Uses 'batch-export' queue and enforces a concurrency limit.
    """
    service = BatchService()
    enqueued_count = service.trigger_batch_render(job_ids)
    
    return {
        "status": "triggered",
        "enqueued": enqueued_count,
        "total_requested": len(job_ids),
        "queue": "batch-export"
    }

@exports_router.post("/batch/zip")
async def download_batch_zip(
    job_ids: list[str],
    user: AuthenticatedUser = Depends(get_current_user)
):
    """
    Creates and downloads a ZIP archive containing all clips from the specified jobs.
    """
    service = BatchService()
    zip_path = service.create_batch_zip(job_ids)
    
    if not zip_path.exists():
        raise HTTPException(status_code=400, detail="No rendered clips found for specified jobs")

    return Response(
        content=zip_path.read_bytes(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_path.name}"}
    )
