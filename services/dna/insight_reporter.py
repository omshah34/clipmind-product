"""File: services/dna/insight_reporter.py
Purpose: Deterministic reporting of DNA weight shifts and milestones.
         Maintains trust by only reporting facts with confidence indicators.
"""

import logging
from typing import Any
from db.repositories.content_dna import log_dna_shift

logger = logging.getLogger(__name__)

# Reliability Thresholds
INITIAL_THRESHOLD = 5
EMERGING_THRESHOLD = 20
STABLE_THRESHOLD = 50
SOLID_THRESHOLD = 150

class InsightReporter:
    def __init__(self):
        pass

    def calculate_confidence(self, signal_count: int) -> dict[str, Any]:
        """Determine reliability rating based on sample size."""
        if signal_count < INITIAL_THRESHOLD:
            return {"label": "Insufficient", "score": 0.1, "color": "gray"}
        if signal_count < EMERGING_THRESHOLD:
            return {"label": "Initial", "score": 0.3, "color": "blue"}
        if signal_count < STABLE_THRESHOLD:
            return {"label": "Emerging", "score": 0.6, "color": "orange"}
        if signal_count < SOLID_THRESHOLD:
            return {"label": "Stable", "score": 0.8, "color": "green"}
        return {"label": "Rock-Solid", "score": 1.0, "color": "gold"}

    def generate_shift_report(
        self, 
        dimension: str, 
        old_val: float, 
        new_val: float, 
        sample_size: int
    ) -> str:
        """Create a human-readable string for weight shifts."""
        delta = new_val - old_val
        direction = "increased" if delta > 0 else "decreased"
        percentage = abs(round((delta / old_val) * 100)) if old_val != 0 else 0
        
        return f"Your preference for {dimension.replace('_weight', '').capitalize()} has {direction} by {percentage}% based on your recent activity."

    def log_significant_shift(
        self, 
        user_id: str, 
        dimension: str, 
        old_val: float, 
        new_val: float, 
        sample_size: int
    ) -> bool:
        """Log shift to history if it exceeds the 0.05 threshold."""
        if abs(new_val - old_val) < 0.05:
            return False
            
        try:
            log_dna_shift(
                user_id=user_id,
                log_type="weight_shift",
                dimension=dimension,
                old_value=old_val,
                new_value=new_val,
                reasoning_code="THRESHOLD_EXCEEDED",
                sample_size=sample_size
            )
            return True
        except Exception as exc:
            logger.error("Failed to log DNA shift: %s", exc)
            return False

def get_insight_reporter() -> InsightReporter:
    return InsightReporter()
