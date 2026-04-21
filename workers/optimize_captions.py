"""File: workers/optimize_captions.py
Purpose: AI-powered caption optimization for multi-platform publishing.
         Generates platform-specific captions using LLM.
"""

from __future__ import annotations

import logging
from uuid import UUID

from workers.celery_app import celery_app
from db.repositories.jobs import get_job
from services.llm_integration import optimize_captions_with_llm, is_llm_available


logger = logging.getLogger(__name__)


@celery_app.task(bind=True, max_retries=2)
def optimize_captions_for_platforms(
    self,
    user_id: str | UUID,
    job_id: str | UUID,
    clip_index: int,
    original_caption: str,
    platforms: list[str],
) -> dict:
    """Generate platform-optimized captions using LLM.
    
    Different platforms have different audience expectations:
    - TikTok: Trendy, emoji-heavy, conversation style
    - Instagram: Lifestyle, aspirational, proper punctuation
    - YouTube: SEO-optimized, educational, detailed
    
    Args:
        user_id: User ID
        job_id: Job UUID
        clip_index: Clip index
        original_caption: Original caption from clip
        platforms: List of platforms to optimize for
    
    Returns:
        Platform-specific caption variants
    """
    user_id = UUID(user_id) if isinstance(user_id, str) else user_id
    job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    
    try:
        logger.info(f"Optimizing captions for platforms: {platforms}")
        
        # Validate platforms
        valid_platforms = {"tiktok", "instagram", "youtube", "linkedin"}
        for p in platforms:
            if p not in valid_platforms:
                logger.warning(f"Unknown platform: {p}")
        
        # Get job context
        job = get_job(job_id)
        if not job or job.status != "completed":
            logger.error(f"Job {job_id} not ready")
            return {"status": "failed", "error": "Job not completed"}
        
        if clip_index >= len(job.clips_json or []):
            logger.error(f"Clip index {clip_index} out of range")
            return {"status": "failed", "error": "Clip index out of range"}
        
        clip = job.clips_json[clip_index]
        clip_topic = clip.reason or ""
        
        # Use LLM for caption optimization (with fallback to heuristic)
        logger.info(f"Optimizing captions using {'LLM' if is_llm_available() else 'heuristic'}")
        llm_result = optimize_captions_with_llm(
            str(user_id),
            str(job_id),
            clip_index,
            original_caption,
            platforms,
        )
        
        platform_captions = llm_result.get("captions", {})
        
        logger.info(f"Generated captions for {len(platform_captions)} platforms using {llm_result.get('method', 'unknown')}")
        
        return {
            "status": "optimized",
            "original_caption": original_caption,
            "platform_captions": platform_captions,
            "method": llm_result.get("method", "unknown"),
            "model": llm_result.get("model"),
        }
    
    except Exception as exc:
        logger.exception(f"Caption optimization failed: {exc}")
        
        try:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        except Exception:
            return {"status": "failed", "error": str(exc)}


def generate_platform_caption(
    original_caption: str,
    platform: str,
    clip_topic: str,
) -> str:
    """Generate platform-specific caption variant.
    
    In production, this would call an LLM (GPT-4, Claude) with
    platform-specific instructions.
    
    For now, uses heuristics to adapt caption tone/style.
    """
    
    if not original_caption:
        original_caption = clip_topic or "Check this out! 🎬"
    
    # Platform-specific guidelines
    if platform == "tiktok":
        # TikTok: Trendy, emoji-heavy, calls for interaction
        caption = f"POV: {original_caption} 🔥\n\n✨ #FYP #For You #Trending #viral"
        if len(caption) > 150:
            caption = f"{original_caption} 🔥 #FYP #ForYou"
    
    elif platform == "instagram":
        # Instagram: Aspirational, proper grammar, strategic hashtags
        caption = f"{original_caption}\n\n✨ Swipe for more 👉\n\n#Instagram #Content #Creator"
        # Instagram captions typically more polished
        if "!" in original_caption:
            caption = caption.replace("!", ".")
    
    elif platform == "youtube":
        # YouTube: SEO-optimized, descriptive, timestamps-friendly
        caption = f"🎬 {original_caption}\n\nStay tuned for more amazing content!\n\n📌 Subscribe for more"
        # YouTube allows longer descriptions
        caption += f"\n\nTopic: {clip_topic}" if clip_topic else ""
    
    elif platform == "linkedin":
        # LinkedIn: Professional, value-focused, industry language
        caption = f"Exciting development: {original_caption}\n\nKey takeaways:\n• Professional quality content\n• Engaging storytelling\n\n#ThoughtLeadership #ContentMarketing"
    
    else:
        # Default fallback
        caption = original_caption
    
    return caption.strip()
