"""File: workers/track_signals.py
Purpose: Signal tracking and Content DNA weight recalculation.
         Aggregates user engagement signals and updates personalized weights.
"""

from __future__ import annotations

import logging
import json
from uuid import UUID
from collections import Counter

from workers.celery_app import celery_app
from db.repositories.content_dna import (
    get_user_signals,
    get_user_score_weights,
    update_user_score_weights,
    log_dna_shift,
)
from services.dna.insight_reporter import get_insight_reporter


logger = logging.getLogger(__name__)


@celery_app.task(bind=True)
def aggregate_user_signals(
    self,
    user_id: str | UUID,
    recalculate_weights: bool = True,
) -> dict:
    """Aggregate user engagement signals and optionally recalculate weights.
    
    Looks at user's signal history and determines:
    1. Which dimensions (hook, emotion, clarity, story, virality) matter most
    2. Confidence score based on sample size
    3. Learning status (learning → converging → optimized)
    
    Args:
        user_id: User ID
        recalculate_weights: Whether to trigger weight recalculation
    
    Returns:
        Signal aggregation results and updated weights
    """
    user_id = UUID(user_id) if isinstance(user_id, str) else user_id
    
    try:
        logger.info(f"Aggregating signals for user {user_id}")
        
        # Get all user signals
        signals = get_user_signals(user_id, limit=500)
        
        if not signals:
            logger.info(f"No signals yet for user {user_id}")
            return {"status": "no_data", "user_id": str(user_id)}
        
        logger.info(f"Found {len(signals)} signals for user {user_id}")
        
        # Analyze signal patterns
        signal_analysis = analyze_signals(signals)
        
        if recalculate_weights and len(signals) >= 5:
            # Recalculate personalized weights
            new_weights = calculate_optimal_weights(signal_analysis)
            
            # Calculate confidence score based on sample size
            # More signals = higher confidence, capped at 1.0
            confidence_score = min(len(signals) / 250.0, 1.0)
            
            # 1. Fetch old weights for comparison
            old_weights_record = get_user_score_weights(user_id)
            old_weights = old_weights_record.get("weights", {}) if old_weights_record else {}

            # 2. Update weights in database
            weights_record = update_user_score_weights(
                user_id=user_id,
                weights=new_weights,
                signal_count=len(signals),
                confidence_score=confidence_score,
            )
            
            # 3. Log significant shifts via InsightReporter
            reporter = get_insight_reporter()
            for dim, new_val in new_weights.items():
                old_val = old_weights.get(dim, 1.0) # Default to 1.0
                reporter.log_significant_shift(
                    user_id=str(user_id),
                    dimension=dim,
                    old_val=old_val,
                    new_val=new_val,
                    sample_size=len(signals)
                )
            
            if weights_record:
                logger.info(f"Updated weights for user {user_id}: confidence={confidence_score}")
                
                return {
                    "status": "optimized",
                    "user_id": str(user_id),
                    "signal_count": len(signals),
                    "confidence_score": confidence_score,
                    "new_weights": new_weights,
                    "signal_analysis": signal_analysis,
                }
        
        return {
            "status": "analyzed",
            "user_id": str(user_id),
            "signal_count": len(signals),
            "signal_analysis": signal_analysis,
        }
    
    except Exception as exc:
        logger.exception(f"Signal aggregation failed: {exc}")
        return {"status": "failed", "error": str(exc)}


def analyze_signals(signals: list[dict]) -> dict:
    """Analyze signal patterns to understand user preferences.
    
    Returns statistics about which signals indicate good vs bad outcomes.
    """
    
    # Categorize signals
    downloaded = sum(1 for s in signals if s.get("signal_type") == "downloaded")
    skipped = sum(1 for s in signals if s.get("signal_type") == "skipped")
    edited = sum(1 for s in signals if s.get("signal_type") == "edited")
    regenerated = sum(1 for s in signals if s.get("signal_type") == "regenerated")
    published = sum(1 for s in signals if s.get("signal_type") == "published")
    
    total = len(signals)
    
    return {
        "total_signals": total,
        "downloaded": downloaded,
        "skipped": skipped,
        "edited": edited,
        "regenerated": regenerated,
        "published": published,
        "download_rate": downloaded / total if total > 0 else 0.0,
        "skip_rate": skipped / total if total > 0 else 0.0,
        "publish_rate": published / total if total > 0 else 0.0,
        "engagement_level": "high" if published >= total * 0.1 else "medium" if downloaded >= total * 0.2 else "low",
    }


def calculate_optimal_weights(signal_analysis: dict) -> dict:
    """Calculate personalized clip scoring weights based on signals.
    
    Uses signal patterns to determine which dimensions correlate
    with downloads, edits, and publications.
    
    Default weights assume all dimensions equally important (1.0).
    Weights adjust based on user behavior patterns.
    """
    
    # Base weights
    weights = {
        "hook": 1.0,
        "emotion": 1.0,
        "clarity": 1.0,
        "story": 1.0,
        "virality": 1.0,
    }
    
    # Adjust based on engagement level
    engagement = signal_analysis.get("engagement_level", "medium")
    
    if engagement == "low":
        # Low engagement: increase hook and virality
        weights["hook"] *= 1.3
        weights["virality"] *= 1.2
        weights["clarity"] *= 1.1
    
    elif engagement == "high":
        # High engagement: user values story and emotional content
        weights["story"] *= 1.4
        weights["emotion"] *= 1.3
    
    # Adjust based on publication rate
    publish_rate = signal_analysis.get("publish_rate", 0.0)
    
    if publish_rate > 0.15:
        # User frequently publishes: prioritize viral potential
        weights["virality"] *= 1.2
    elif publish_rate > 0.05:
        # Moderate publishing: balance is working
        pass
    else:
        # Low publishing rate: focus on hooks and clarity
        weights["hook"] *= 1.2
        weights["clarity"] *= 1.1
    
    # Adjust based on edit rate (implied from regeneration)
    regenerate_rate = signal_analysis.get("regenerated", 0) / signal_analysis.get("total_signals", 1)
    
    if regenerate_rate > 0.1:
        # User frequently regenerates: emphasize clarity and story
        weights["clarity"] *= 1.2
        weights["story"] *= 1.1
    
    # Normalize weights to avoid extreme values
    # Multiply by 10 to shift from small decimals to round numbers
    max_weight = max(weights.values())
    total = sum(weights.values())
    
    # Scale so they're reasonable magnitudes
    for key in weights:
        weights[key] = round(weights[key], 2)
    
    return weights


@celery_app.task(bind=True)
def trigger_ml_weight_optimization(
    self,
    user_id: str | UUID,
) -> dict:
    """Trigger external ML service for advanced weight optimization.
    
    This would call a machine learning service (Weights & Biases,
    or a custom ML endpoint) to perform advanced optimization.
    
    For now, uses the heuristic-based approach above.
    """
    user_id = UUID(user_id) if isinstance(user_id, str) else user_id
    
    try:
        logger.info(f"Triggering ML optimization for user {user_id}")
        
        # Call aggregate_user_signals which handles the optimization
        result = aggregate_user_signals.apply_async(
            args=[str(user_id)],
            kwargs={"recalculate_weights": True},
        )
        
        return {
            "status": "optimization_queued",
            "task_id": str(result.id),
            "user_id": str(user_id),
        }
    
    except Exception as exc:
        logger.exception(f"ML optimization trigger failed: {exc}")
        return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True)
def get_weight_learning_status(
    self,
    user_id: str | UUID,
) -> dict:
    """Get current learning status for user's personalization.
    
    Returns:
        Learning status (learning/converging/optimized) based on signal count
    """
    user_id = UUID(user_id) if isinstance(user_id, str) else user_id
    
    try:
        # Get current weights and signal count
        weights = get_user_score_weights(user_id)
        
        if not weights:
            return {
                "status": "newuser",
                "learning_status": "learning",
                "signal_count": 0,
                "confidence_score": 0.0,
            }
        
        signal_count = weights.get("signal_count", 0)
        confidence = weights.get("confidence_score", 0.0)
        
        # Determine learning status
        if signal_count < 50:
            learning_status = "learning"
            description = "Initial learning phase - keep engaging!"
        elif signal_count < 200:
            learning_status = "converging"
            description = "Pattern emerging - system converging"
        else:
            learning_status = "optimized"
            description = "Personalization optimized!"
        
        return {
            "status": "success",
            "learning_status": learning_status,
            "signal_count": signal_count,
            "confidence_score": confidence,
            "next_milestone": 50 if signal_count < 50 else 200 if signal_count < 200 else None,
            "description": description,
        }
    
    except Exception as exc:
        logger.exception(f"Status check failed: {exc}")
        return {"status": "failed", "error": str(exc)}
