"""
File: services/llm_integration.py
Purpose: LLM-powered sequence detection and caption optimization.
         Uses OpenAI GPT-4 with fallback to heuristics on failure.
"""

import json
import os
from typing import Optional
from tenacity import retry, stop_after_attempt, wait_exponential
from openai import OpenAI, RateLimitError, APIError

from core.config import settings
from db.repositories.jobs import get_job
from services.openai_client import make_openai_client

def detect_sequences_heuristic(user_id: str, job_id: str) -> dict:
    job = get_job(job_id)
    clips = job.get("clips_json", []) if job else []
    sequences = []
    for i in range(0, len(clips), 3):
        chunk = clips[i:i+3]
        if not chunk: continue
        sequences.append({
            "clip_indices": list(range(i, i+len(chunk))),
            "narrative_arc": f"Simple progression cluster",
            "narrative_coherence": 0.5,
            "cliffhanger_scores": [0.5] * len(chunk)
        })
    return {"method": "heuristic", "sequences": sequences, "analysis": "Fallback sequential grouping"}

def generate_platform_caption(original: str, platform: str) -> str:
    tags = {"tiktok": "#FYP #Viral", "instagram": "#Instagram #Creator", "youtube": "#Shorts #Video", "linkedin": "#Business"}
    return f"{original}\n\n{tags.get(platform, '#Content')}"


# Initialize OpenAI client (respects OPENAI_BASE_URL if set)
OPENAI_API_KEY = settings.openai_api_key
llm_client = make_openai_client() if OPENAI_API_KEY else None


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def detect_sequences_with_llm(user_id: str, job_id: str) -> dict:
    """
    Detect clip sequences using GPT-4 semantic understanding.
    Falls back to heuristic if LLM is unavailable or fails.
    
    Args:
        user_id: User ID for signal logging
        job_id: Job ID to analyze
        
    Returns:
        Dictionary with sequences and analysis metadata
    """
    try:
        # Get job data
        job = get_job(job_id)
        if not job or not job.get("clips_json"):
            raise ValueError(f"Job {job_id} not found or has no clips")
        
        clips = job["clips_json"]
        
        # If LLM not configured, use heuristic
        if not llm_client:
            print(f"LLM not configured, falling back to heuristic for job {job_id}")
            return detect_sequences_heuristic(user_id, job_id)
        
        # Prepare clip summaries for LLM
        clip_summaries = []
        for idx, clip in enumerate(clips):
            clip_summaries.append({
                "index": idx,
                "duration": clip.get("duration", 5),
                "title": clip.get("title", f"Clip {idx}"),
                "hook_score": clip.get("hook_score", 0.5),
                "virality_score": clip.get("virality_score", 0.5),
                "emotion_score": clip.get("emotion_score", 0.5),
                "story_score": clip.get("story_score", 0.5),
            })
        
        # Call LLM to analyze sequences
        prompt = f"""Analyze these video clips and suggest multi-clip narrative sequences (stories) that would work well together.

Clips:
{json.dumps(clip_summaries, indent=2)}

Requirements:
1. Each sequence should have 3-5 clips maximum
2. Sequences should have rising tension/cliffhanger scores (0.5 → 0.9)
3. Suggest consecutive clip groupings that form compelling narratives
4. Provide a "narrative_arc" description for each sequence
5. Score each sequence from 0-1 on "narrative_coherence"

Return ONLY valid JSON with this structure:
{{
  "sequences": [
    {{
      "clip_indices": [0, 1, 2],
      "narrative_arc": "Brief story arc description",
      "narrative_coherence": 0.85,
      "cliffhanger_scores": [0.5, 0.7, 0.9]
    }}
  ],
  "analysis": "Brief analysis of detected patterns"
}}
"""
        
        response = llm_client.chat.completions.create(
            model=settings.clip_detector_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert video editor analyzing clip sequences for narrative storytelling.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=1000,
        )
        
        # Parse LLM response
        content = response.choices[0].message.content
        # Extract JSON from markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content.strip())
        
        return {
            "method": "llm",
            "sequences": result.get("sequences", []),
            "analysis": result.get("analysis", ""),
            "model": settings.clip_detector_model,
        }
        
    except (RateLimitError, APIError) as e:
        print(f"LLM API error for job {job_id}: {e}. Using heuristic fallback.")
        return detect_sequences_heuristic(user_id, job_id)
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"LLM parsing error for job {job_id}: {e}. Using heuristic fallback.")
        return detect_sequences_heuristic(user_id, job_id)
    except Exception as e:
        print(f"Unexpected LLM error for job {job_id}: {e}. Using heuristic fallback.")
        return detect_sequences_heuristic(user_id, job_id)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
def optimize_captions_with_llm(
    user_id: str,
    job_id: str,
    clip_index: int,
    original_caption: str,
    platforms: list,
) -> dict:
    """
    Optimize captions for specific platforms using GPT-4.
    Falls back to heuristic if LLM is unavailable or fails.
    
    Args:
        user_id: User ID
        job_id: Job ID for context
        clip_index: Clip index
        original_caption: Original caption text
        platforms: List of target platforms (tiktok, instagram, youtube, linkedin)
        
    Returns:
        Dictionary with optimized captions per platform
    """
    try:
        # Get job context
        job = get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        # If LLM not configured, use heuristic
        if not llm_client:
            print(f"LLM not configured, falling back to heuristic for captions")
            return {
                platform: generate_platform_caption(original_caption, platform)
                for platform in platforms
            }
        
        # Build platform context
        platform_context = {
            "tiktok": {
                "max_chars": 2200,
                "tone": "trendy, energetic",
                "typical_hashtags": "#FYP #Viral #Trending #ForYou",
                "platform_rules": "Trending sounds are crucial, emojis drive engagement, keep text punchy",
            },
            "instagram": {
                "max_chars": 2200,
                "tone": "aspirational, polished",
                "typical_hashtags": "#Instagram #Content #Creator #Explore",
                "platform_rules": "Aesthetic consistency matters, call-to-action important, captions tell story",
            },
            "youtube": {
                "max_chars": 5000,
                "tone": "professional, SEO-optimized",
                "typical_hashtags": "#YouTube #Video #Subscribe #Content",
                "platform_rules": "First line critical (clickthrough driver), SEO keywords essential, longer form OK",
            },
            "linkedin": {
                "max_chars": 3000,
                "tone": "professional, thought-leadership",
                "typical_hashtags": "#LinkedIn #Professional #Business #Career",
                "platform_rules": "Professional tone required, insights over promotion, engagement through questions",
            },
        }
        
        # Filter to requested platforms
        requested_platforms = {p: platform_context.get(p) for p in platforms if p in platform_context}
        
        prompt = f"""You are a social media expert. Optimize this video caption for multiple platforms.

Original Caption:
"{original_caption}"

Target Platforms:
{json.dumps(requested_platforms, indent=2)}

For each platform, create an optimized caption that:
1. Fits the platform's maximum character limit
2. Uses the tone and rules specified
3. Includes relevant hashtags
4. Maximizes engagement potential
5. Maintains the core message from the original

Return ONLY valid JSON with this structure:
{{
  "optimized_captions": {{
    "tiktok": "...",
    "instagram": "...",
    "youtube": "...",
    "linkedin": "..."
  }},
  "strategy": "Brief strategy explanation"
}}

Only include keys for platforms in the target list above.
"""
        
        response = llm_client.chat.completions.create(
            model=settings.clip_detector_model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert social media strategist optimizing content for maximum engagement.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.8,
            max_tokens=800,
        )
        
        # Parse LLM response
        content = response.choices[0].message.content
        # Extract JSON from markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        result = json.loads(content.strip())
        optimized = result.get("optimized_captions", {})
        
        return {
            "method": "llm",
            "captions": optimized,
            "strategy": result.get("strategy", ""),
            "model": settings.clip_detector_model,
        }
        
    except (RateLimitError, APIError) as e:
        print(f"LLM API error for captions: {e}. Using heuristic fallback.")
        return {
            "method": "heuristic",
            "captions": {
                platform: generate_platform_caption(original_caption, platform)
                for platform in platforms
            },
        }
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        print(f"LLM parsing error for captions: {e}. Using heuristic fallback.")
        return {
            "method": "heuristic",
            "captions": {
                platform: generate_platform_caption(original_caption, platform)
                for platform in platforms
            },
        }
    except Exception as e:
        print(f"Unexpected LLM error for captions: {e}. Using heuristic fallback.")
        return {
            "method": "heuristic",
            "captions": {
                platform: generate_platform_caption(original_caption, platform)
                for platform in platforms
            },
        }


def is_llm_available() -> bool:
    """Check if LLM is configured and available."""
    return llm_client is not None and OPENAI_API_KEY != ""
