"""File: api/routes/content_dna.py
Purpose: Content DNA / creator profile endpoints. 
         Provides transparency into how the AI learns from the user.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from typing import Any
from uuid import UUID

from db.repositories.content_dna import (
    get_user_score_weights,
    get_user_signal_counts,
    update_user_score_weights,
    get_dna_history,
    get_latest_executive_summary,
)
from workers.dna_tasks import generate_executive_summary as trigger_summary_task
from services.dna.insight_reporter import get_insight_reporter
from services.dna.content_advisor import get_content_advisor
from services.content_dna import record_signal, POSITIVE_SIGNALS, NEGATIVE_SIGNALS
from api.dependencies import get_current_user, AuthenticatedUser

router = APIRouter(prefix="/dna", tags=["content_dna"])

# Note: In a real app, we'd have proper auth
# Removed MOCK_USER_ID


@router.get("/weights")
def get_weights(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Retrieve the current personalized weights and learning status for a user."""
    user_id = str(user.user_id)
    dna_data = get_user_score_weights(user_id)
    signal_counts = get_user_signal_counts(user_id)
    
    if not dna_data:
        # Initial state
        return {
            "user_id": user_id,
            "learning_status": "learning",
            "confidence_score": 0.0,
            "score_weights": {
                "hook": 1.0,
                "emotion": 1.0,
                "clarity": 1.0,
                "story": 1.0,
                "virality": 1.0,
            },
            "signals": {
                "total_signals": 0,
                "downloaded_count": 0,
                "skipped_count": 0,
                "edited_count": 0,
                "regenerated_count": 0,
                "published_count": 0,
            },
            "recommendations": [
                "Upload and interact with at least 10 clips to start personalizing your DNA."
            ],
            "progress_to_next": {
                "label": "Converging",
                "percentage": 0,
                "signals_needed": 10
            },
            "manual_overrides": []
        }

    # Map database weight keys back to frontend keys
    db_weights = dna_data["weights"]
    weights = {
        "hook": db_weights.get("hook_weight", 1.0),
        "emotion": db_weights.get("emotion_weight", 1.0),
        "clarity": db_weights.get("clarity_weight", 1.0),
        "story": db_weights.get("story_weight", 1.0),
        "virality": db_weights.get("virality_weight", 1.0),
    }

    signal_count = dna_data["signal_count"]
    confidence_info = get_insight_reporter().calculate_confidence(signal_count)
    
    # 1. Segregated Reporting Logic
    reporter = get_insight_reporter()
    insights = []
    history = get_dna_history(user_id, limit=5)
    for log in history:
        if log["log_type"] == "weight_shift":
            insights.append({
                "type": "obs",
                "message": reporter.generate_shift_report(
                    log["dimension"], 
                    log["old_value"], 
                    log["new_value"], 
                    log["sample_size"]
                ),
                "confidence": confidence_info["label"]
            })
    
    # 2. Segregated Recommendation Logic
    advisor = get_content_advisor()
    recommendations = advisor.get_recommendations(
        weights, 
        signal_counts, 
        confidence_info["label"]
    )

    # 3. Learning Path (Progressive Disclosure)
    status = "learning"
    if signal_count >= 100:
        status = "optimized"
    elif signal_count >= 20:
        status = "converging"

    return {
        "user_id": user_id,
        "learning_status": status,
        "confidence": confidence_info,
        "score_weights": weights,
        "signals": {
            "total_signals": signal_count,
            "counts": signal_counts
        },
        "executive_summary": get_latest_executive_summary(user_id),
        "insights": insights[:3],
        "recommendations": recommendations,
        "history_log": history
    }


@router.post("/overrides")
def post_overrides(
    dimension: str, 
    locked: bool, 
    user: AuthenticatedUser = Depends(get_current_user)
) -> dict:
    """Lock or unlock a specific scoring dimension from automated updates."""
    user_id = str(user.user_id)
    dna_data = get_user_score_weights(user_id)
    if not dna_data:
        raise HTTPException(status_code=404, detail="DNA profile not found")
    
    # Internal weight keys use _weight suffix
    weight_key = f"{dimension}_weight" 
    overrides = dna_data.get("manual_overrides", [])
    
    if locked:
        if weight_key not in overrides:
            overrides.append(weight_key)
    else:
        if weight_key in overrides:
            overrides.remove(weight_key)
    
    update_user_score_weights(
        user_id, 
        dna_data["weights"], 
        dna_data["signal_count"], 
        dna_data["confidence_score"],
        overrides
    )
    
    return {"status": "success", "manual_overrides": overrides}


@router.get("/summary")
def get_summary(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Retrieve the latest synthetic strategy summary."""
    user_id = str(user.user_id)
    summary = get_latest_executive_summary(user_id)
    if not summary:
        raise HTTPException(status_code=404, detail="No summary found. Try generating one.")
    return summary


@router.post("/summary/generate")
def post_generate_summary(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    """Manually trigger an LLM-based strategy synthesis."""
    user_id = str(user.user_id)
    task = trigger_summary_task.delay(user_id)
    return {"status": "accepted", "task_id": task.id, "message": "Strategy synthesis started in background."}
