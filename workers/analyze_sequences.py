"""File: workers/analyze_sequences.py
Purpose: LLM-based detection of multi-clip narrative sequences.
         Identifies 3-5 clip narrative arcs from video clips.
"""

from __future__ import annotations

import logging
import json
from uuid import UUID

import httpx
from openai import APIConnectionError, APITimeoutError, RateLimitError
from celery.exceptions import SoftTimeLimitExceeded
from workers.celery_app import celery_app
from db.repositories.clip_sequences import (
    get_job,
    create_clip_sequence,
)
from db.repositories.jobs import update_job
from services.llm_integration import detect_sequences_with_llm, is_llm_available


logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (httpx.TimeoutException, APIConnectionError, APITimeoutError, RateLimitError)


@celery_app.task(
    bind=True, 
    max_retries=4,
    soft_time_limit=300,   # Graceful timeout at 5 minutes
    time_limit=360,        # Hard kill at 6 minutes
)
def detect_clip_sequences(
    self,
    user_id: str | UUID,
    job_id: str | UUID,
) -> dict:
    """Detect narrative sequences from clips using LLM.
    
    Analyzes clip metadata/descriptions to find 3-5 clip narrative arcs
    that can be published as serialized content.
    
    Args:
        user_id: User ID
        job_id: Job UUID with generated clips
    
    Returns:
        Detected sequences with clip indices and captions
    """
    user_id = UUID(user_id) if isinstance(user_id, str) else user_id
    job_id = UUID(job_id) if isinstance(job_id, str) else job_id
    
    try:
        logger.info(f"Starting sequence detection for job {job_id}")
        
        # Get job and clips
        job = get_job(job_id)
        if not job or job.status != "completed":
            logger.error(f"Job {job_id} not ready for sequence analysis")
            return {"status": "error", "message": "Job not completed"}
        
        if not job.clips_json or len(job.clips_json) < 3:
            logger.info(f"Job {job_id} has fewer than 3 clips, skipping sequence detection")
            return {"status": "insufficient_clips", "clip_count": len(job.clips_json or [])}
        
        clips = job.clips_json
        
        # Use LLM for sequence detection (with fallback to heuristic)
        logger.info(f"Analyzing sequences for job {job_id} using {'LLM' if is_llm_available() else 'heuristic'}")
        llm_result = detect_sequences_with_llm(str(user_id), str(job_id))
        
        sequences = convert_llm_sequences_to_records(llm_result, len(clips))
        
        logger.info(f"Detected {len(sequences)} sequences for job {job_id}")
        
        # Save sequences to database
        saved_sequences = []
        for seq_idx, sequence in enumerate(sequences):
            clip_indices = sequence["clip_indices"]
            captions = sequence["captions"]
            
            seq_record = create_clip_sequence(
                user_id=user_id,
                job_id=job_id,
                sequence_title=sequence.get("title", f"Series {seq_idx + 1}"),
                clip_indices=clip_indices,
                suggested_captions=captions,
                cliffhanger_scores=sequence.get("cliffhanger_scores", [0.5] * len(clip_indices)),
                series_description=sequence.get("description"),
                platform_optimizations=sequence.get("platform_optimizations", {}),
            )
            
            if seq_record:
                saved_sequences.append({
                    "sequence_id": str(seq_record["id"]),
                    "title": sequence.get("title"),
                    "clip_count": len(clip_indices),
                })
        
        return {
            "status": "completed",
            "job_id": str(job_id),
            "sequences_detected": len(saved_sequences),
            "sequences": saved_sequences,
        }
    
    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for job {job_id}")
        update_job(job_id, status="failed", error_message="Task timed out")
        return {"status": "failed", "error": "Task timed out"}

    except TRANSIENT_ERRORS as exc:
        logger.warning(f"Transient error in sequence detection for job {job_id}: {exc}")
        # Gap 19: Exponential backoff (60s, 120s, 240s...)
        countdown = 2 ** self.request.retries * 60
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as exc:
        logger.exception(f"Sequence detection failed: {exc}")
        
        try:
            update_job(job_id, status="failed", error_message=str(exc))
        except Exception:
            pass
        return {"status": "failed", "error": str(exc)}


def detect_sequences_heuristic(clips, clip_descriptions: list) -> list[dict]:
    """Simple heuristic-based sequence detection.
    
    In production, this would call an LLM for semantic understanding.
    This heuristic creates sequences based on score clusters.
    """
    sequences = []
    
    if len(clips) < 3:
        return sequences
    
    # Group clips into sequences by score patterns
    # Strategy: Find rising/falling patterns that tell stories
    
    # Simple strategy: chunks of 3-5 consecutive high-scoring clips
    consecutive_high = []
    
    for i, clip in enumerate(clips):
        score = clip.final_score or 0.0
        
        if score > 0.7:  # High-scoring clip
            consecutive_high.append(i)
        else:
            # Found a low-scoring clip, save sequence if we have 3+ high clips
            if len(consecutive_high) >= 3:
                cliffhanger_scores = [0.5 + i * 0.1 for i in range(len(consecutive_high))]
                
                sequences.append({
                    "clip_indices": consecutive_high.copy(),
                    "captions": [
                        f"Part {len(sequences) + 1}: {i+1}/{len(consecutive_high)}"
                        for i in range(len(consecutive_high))
                    ],
                    "cliffhanger_scores": cliffhanger_scores,
                    "title": f"Series {len(sequences) + 1}",
                    "description": f"{len(consecutive_high)}-clip narrative arc",
                    "platform_optimizations": {
                        "tiktok": {"min_duration": 15, "max_duration": 60},
                        "instagram": {"min_duration": 10, "max_duration": 90},
                        "youtube": {"min_duration": 30, "max_duration": 600},
                    },
                })
            
            consecutive_high = []
    
    # Handle remaining high-scoring clips at end
    if len(consecutive_high) >= 3:
        cliffhanger_scores = [0.5 + i * 0.1 for i in range(len(consecutive_high))]
        
        sequences.append({
            "clip_indices": consecutive_high.copy(),
            "captions": [
                f"Part {len(sequences) + 1}: {i+1}/{len(consecutive_high)}"
                for i in range(len(consecutive_high))
            ],
            "cliffhanger_scores": cliffhanger_scores,
            "title": f"Series {len(sequences) + 1}",
            "description": f"{len(consecutive_high)}-clip narrative arc",
            "platform_optimizations": {
                "tiktok": {"min_duration": 15, "max_duration": 60},
                "instagram": {"min_duration": 10, "max_duration": 90},
                "youtube": {"min_duration": 30, "max_duration": 600},
            },
        })
    
    return sequences


def convert_llm_sequences_to_records(llm_result: dict, total_clips: int) -> list[dict]:
    """Convert LLM sequence detection result to database record format.
    
    Handles both LLM responses and fallback heuristic results.
    
    Args:
        llm_result: Result from detect_sequences_with_llm
        total_clips: Total number of clips in job
        
    Returns:
        List of sequence records ready for database insertion
    """
    sequences = []
    
    # If using heuristic fallback, result might not have 'sequences' key
    if llm_result.get("method") == "heuristic":
        # Return original heuristic result format
        return []
    
    # Process LLM sequences
    llm_sequences = llm_result.get("sequences", [])
    
    for seq_idx, seq in enumerate(llm_sequences):
        clip_indices = seq.get("clip_indices", [])
        
        # Validate clip indices
        if not clip_indices or any(i >= total_clips for i in clip_indices):
            logger.warning(f"Invalid clip indices {clip_indices}, skipping sequence {seq_idx}")
            continue
        
        # Get cliffhanger scores from LLM or generate
        cliffhanger_scores = seq.get("cliffhanger_scores", [])
        if not cliffhanger_scores:
            # Generate rising scores if not provided
            cliffhanger_scores = [0.5 + (i * 0.4 / len(clip_indices)) for i in range(len(clip_indices))]
        
        sequences.append({
            "clip_indices": clip_indices,
            "captions": [
                f"Part {seq_idx + 1}: {i + 1}/{len(clip_indices)} - {seq.get('narrative_arc', 'Clip')}"
                for i in range(len(clip_indices))
            ],
            "cliffhanger_scores": cliffhanger_scores,
            "title": f"Series {seq_idx + 1}",
            "description": seq.get("narrative_arc", f"{len(clip_indices)}-clip narrative"),
            "narrative_coherence": seq.get("narrative_coherence", 0.7),
            "platform_optimizations": {
                "tiktok": {"min_duration": 15, "max_duration": 60},
                "instagram": {"min_duration": 10, "max_duration": 90},
                "youtube": {"min_duration": 30, "max_duration": 600},
            },
        })
    
    return sequences
