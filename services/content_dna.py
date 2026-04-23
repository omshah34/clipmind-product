"""File: services/content_dna.py
Purpose: Personalization engine that learns from user behavior.
         Records signals (download, publish, skip) and updates scoring
         weights to prioritize the type of content the user prefers.
"""

from __future__ import annotations

import logging
from typing import Any

from db.repositories.jobs import get_job
from db.repositories.content_dna import (
    get_user_score_weights,
    record_content_signal,
    update_user_score_weights,
)

logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────────────

DIMENSIONS = [
    "hook_score",
    "emotion_score",
    "clarity_score",
    "story_score",
    "virality_score",
]

# Mapping between internal score keys and weight keys
SCORE_TO_WEIGHT = {
    "hook_score": "hook_weight",
    "emotion_score": "emotion_weight",
    "clarity_score": "clarity_weight",
    "story_score": "story_weight",
    "virality_weight": "virality_weight", # Consistent naming across tables
}

# Signal influence
POSITIVE_SIGNALS = ["download", "publish", "edit"]
NEGATIVE_SIGNALS = ["skip", "regenerate"]

LEARNING_RATE = 0.05
MAX_WEIGHT = 2.5
MIN_WEIGHT = 0.5

# Phase 5: Feedback Loop Constants
PERFORMANCE_LEARNING_RATE = 0.10
MAX_PERFORMANCE_SHIFT = 0.15 # ±15% cap
MIN_SAMPLE_SIZE = 5         # n≥5 requirement


def record_signal(
    user_id: str,
    job_id: str,
    clip_index: int,
    signal_type: str,
    metadata: dict | None = None,
) -> None:
    """Record a user signal and update their Content DNA weights."""
    logger.info("[dna] Recording signal: user=%s job=%s type=%s", user_id, job_id, signal_type)
    
    # 1. Persist the signal
    record_content_signal(user_id, job_id, clip_index, signal_type, metadata)
    
    # 2. Update weights
    try:
        _update_weights_from_signal(user_id, job_id, clip_index, signal_type)
    except Exception as exc:
        logger.error("[dna] Failed to update weights for user %s: %s", user_id, exc)


def _update_weights_from_signal(user_id: str, job_id: str, clip_index: int, signal_type: str) -> None:
    """The 'Brain' of Content DNA. Adjusts weights based on evidence."""
    job = get_job(job_id)
    if not job or not job.timeline_json: # timeline_json is used for clips in some contexts
        # Fallback to clips_json if available
        pass

    # Fetch clips
    clips_json = getattr(job, "clips_json", []) or []
    if not clips_json and hasattr(job, "timeline_json"):
        import json
        try:
            timeline = json.loads(job.timeline_json) if isinstance(job.timeline_json, str) else job.timeline_json
            clips_json = timeline.get("clips", [])
        except:
            pass

    if not clips_json:
        return

    # Find the specific clip to see its score profile
    def _get_clip_index(c):
        if isinstance(c, dict):
            return int(c.get("clip_index", -1))
        return getattr(c, "clip_index", -1)

    clip_obj = next((c for c in clips_json if _get_clip_index(c) == clip_index), None)
    if not clip_obj and signal_type != "regenerate":
        return

    # Normalize to dict
    clip = clip_obj if isinstance(clip_obj, dict) else (clip_obj.model_dump() if hasattr(clip_obj, "model_dump") else (vars(clip_obj) if clip_obj else {}))

    # Fetch current weights
    dna_data = get_user_score_weights(user_id)
    if not dna_data:
        # Defaults
        weights = {
            "hook_weight": 1.0,
            "emotion_weight": 1.0,
            "clarity_weight": 1.0,
            "story_weight": 1.0,
            "virality_weight": 1.0,
        }
        signal_count = 0
        confidence = 0.0
    else:
        weights = dna_data["weights"]
        signal_count = dna_data["signal_count"]
        confidence = dna_data["confidence_score"]

    # Simple Bayesian-inspired update:
    modifier = 0.0
    if signal_type in POSITIVE_SIGNALS:
        modifier = LEARNING_RATE
    elif signal_type in NEGATIVE_SIGNALS:
        modifier = -LEARNING_RATE

    if modifier != 0:
        for dim in DIMENSIONS:
            score = float(clip.get(dim, 5.0)) # Default to mid-score if missing
            # If score is high (>7), the dimensions's influence on the signal was high
            if score > 7.0:
                # Update current weight if not manual override
                weight_key = dim.replace("_score", "_weight")
                if weight_key in (dna_data.get("manual_overrides", []) if dna_data else []):
                    continue

                current_w = weights.get(weight_key, 1.0)
                new_w = max(MIN_WEIGHT, min(MAX_WEIGHT, current_w + modifier))
                weights[weight_key] = round(new_w, 3)

    # Special case: regenerate (all weights slightly decreased)
    if signal_type == "regenerate":
        for k in weights:
            weights[k] = max(MIN_WEIGHT, round(weights[k] * 0.95, 3))

    # 3. Update stats
    signal_count += 1
    # Confidence grows with signals, caps at 0.95
    confidence = min(0.95, signal_count / 50.0) 

    update_user_score_weights(user_id, weights, signal_count, confidence, dna_data.get("manual_overrides", []) if dna_data else [])
    logger.debug("[dna] Updated weights for user %s: %s (confidence: %.2f)", user_id, weights, confidence)


def apply_performance_feedback(
    user_id: str,
    job_id: str,
    clip_index: int,
    delta: float,
    milestone_tier: str | None = None,
) -> None:
    """
    Adjust weights based on real-world performance outcomes.
    Implements dampened updates (+/- 15% cap) and sample size gating (n>=5).
    """
    from db.connection import engine
    from sqlalchemy import text
    
    logger.info("[dna] Applying performance feedback: user=%s job=%s delta=%.2f", user_id, job_id, delta)

    # 1. Gate: Minimum Sample Size (n>=5 completed windows)
    query_count = text("""
        SELECT COUNT(*) FROM clip_performance 
        WHERE user_id = :user_id AND window_complete = TRUE
    """)
    with engine.connect() as connection:
        count = connection.execute(query_count, {"user_id": user_id}).scalar()
    
    if count < MIN_SAMPLE_SIZE:
        logger.info("[dna] Performance update deferred: Sample size %d < %d", count, MIN_SAMPLE_SIZE)
        return

    # 2. Logic: Identify which attributes to boost/dampen
    job = get_job(job_id)
    if not job:
        return
        
    clips_json = getattr(job, "clips_json", []) or []
    if not clips_json and hasattr(job, "timeline_json"):
        import json
        try:
            timeline = json.loads(job.timeline_json) if isinstance(job.timeline_json, str) else job.timeline_json
            clips_json = timeline.get("clips", [])
        except:
            pass
            
    if not clips_json:
        return
        
    # Find the specific clip to see its score profile
    def _get_clip_index(c):
        if isinstance(c, dict):
            return int(c.get("clip_index", -1))
        return getattr(c, "clip_index", -1)

    clip_obj = next((c for c in clips_json if _get_clip_index(c) == clip_index), None)
    if not clip_obj:
        return

    # Normalize to dict
    clip = clip_obj if isinstance(clip_obj, dict) else (clip_obj.model_dump() if hasattr(clip_obj, "model_dump") else vars(clip_obj))

    dna_data = get_user_score_weights(user_id)
    weights = dna_data["weights"] if dna_data else {k: 1.0 for k in SCORE_TO_WEIGHT.values()}
    
    # 3. Dampened Update
    modifier = PERFORMANCE_LEARNING_RATE if delta > 0 else -PERFORMANCE_LEARNING_RATE
    
    # Milestone boost
    if milestone_tier == "viral":
        modifier *= 2.0
    
    updated = False
    for dim in DIMENSIONS:
        score = float(clip.get(dim, 5.0))
        if score > 7.5: # Only shift weights for strong attributes
            weight_key = SCORE_TO_WEIGHT.get(dim)
            if weight_key:
                # Check for manual overrides
                overrides = dna_data.get("manual_overrides", []) if dna_data else []
                if weight_key in overrides:
                    continue

                current_w = weights.get(weight_key, 1.0)
                
                # Apply update
                proposed_shift = modifier * (score / 10.0)
                
                # Guard rail: ±15% cap per cycle
                shift = max(-MAX_PERFORMANCE_SHIFT, min(MAX_PERFORMANCE_SHIFT, proposed_shift))
                
                new_w = max(MIN_WEIGHT, min(MAX_WEIGHT, current_w + shift))
                
                if abs(new_w - current_w) > 0.001:
                    weights[weight_key] = round(new_w, 3)
                    updated = True

    if updated:
        update_user_score_weights(
            user_id, 
            weights, 
            dna_data.get("signal_count", 0) if dna_data else 1,
            dna_data.get("confidence_score", 0.1) if dna_data else 0.1,
            dna_data.get("manual_overrides", []) if dna_data else []
        )
        logger.info("[dna] Performance Loop: Applied shift to user %s weights", user_id)
        
        from db.repositories.performance import create_performance_alert
        create_performance_alert(
            user_id=user_id,
            alert_type="weight_shift",
            message=f"Autonomous Update: We've tuned your scoring weights based on recent performance milestones.",
            metadata={"delta": delta, "milestone": milestone_tier}
        )


def get_personalized_weights(user_id: str | None) -> dict:
    """Get weights for the clip detector. Defaults if no user or no DNA."""
    default_weights = {
        "hook_weight": 1.0,
        "emotion_weight": 1.0,
        "clarity_weight": 1.0,
        "story_weight": 1.0,
        "virality_weight": 1.0,
    }
    
    if not user_id:
        return default_weights
        
    dna_data = get_user_score_weights(user_id)
    if not dna_data:
        return default_weights
        
    return dna_data.get("weights", default_weights)
