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

@exports_router.get("/job/{job_id}/premiere-xml")
async def export_premiere_xml(
    job_id: str,
    # user: AuthenticatedUser = Depends(get_current_user) # Disabling for dev mode
):
    """Download Final Cut Pro XML for Premiere/DaVinci integration."""
    engine = get_export_engine()
    xml_content = engine.generate_premiere_xml(job_id)
    if not xml_content:
        raise HTTPException(status_code=404, detail="XML generation failed or no clips found")
    
    return Response(content=xml_content, media_type="application/xml")

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
