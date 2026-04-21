"""File: services/dna/content_advisor.py
Purpose: Rule-based recommendation engine for content strategy.
         Provides proactive advice to help creators optimize their output.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

class ContentAdvisor:
    def __init__(self):
        # Thresholds for trigger logic
        self.UNDERUTILIZED_WEIGHT = 0.85
        self.DOMINANT_WEIGHT = 1.30
        self.MIN_SIGNALS_FOR_ADVICE = 10

    def get_recommendations(
        self, 
        weights: dict[str, float], 
        signal_counts: dict[str, int],
        confidence_label: str
    ) -> list[dict[str, Any]]:
        """Generate proactive recommendations based on weights and signals."""
        recommendations = []
        
        # 1. Check for sufficient data
        total_signals = sum(signal_counts.values())
        if total_signals < self.MIN_SIGNALS_FOR_ADVICE:
            return [{
                "id": "insufficient_data",
                "type": "info",
                "message": f"Keep interacting! Generate {self.MIN_SIGNALS_FOR_ADVICE - total_signals} more clips to unlock personalized advice.",
                "confidence": "Low"
            }]

        # 2. Underutilized Dimension Detection
        # Logic: weight < 0.85 AND skip rate is likely high (implied by weight drop)
        for dim, weight in weights.items():
            if weight < self.UNDERUTILIZED_WEIGHT:
                recommendations.append({
                    "id": f"underutilized_{dim}",
                    "type": "strategy",
                    "message": f"The '{dim.capitalize()}' dimension is currently underperforming in your clips. Try experimenting with more {dim}-focused hooks.",
                    "confidence": confidence_label
                })

        # 3. Dominant Pattern Detection
        # Logic: weight > 1.30 
        for dim, weight in weights.items():
            if weight > self.DOMINANT_WEIGHT:
                recommendations.append({
                    "id": f"dominant_{dim}",
                    "type": "insight",
                    "message": f"Your audience clearly favors '{dim.capitalize()}'. We are prioritizing these clips in your Autopilot queue.",
                    "confidence": confidence_label
                })

        # 4. Empty State Fallback
        if not recommendations:
            recommendations.append({
                "id": "balanced_dna",
                "type": "info",
                "message": "Your content DNA is well-balanced across all dimensions. Carry on!",
                "confidence": confidence_label
            })

        return recommendations

def get_content_advisor() -> ContentAdvisor:
    return ContentAdvisor()
