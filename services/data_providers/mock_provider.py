"""File: services/data_providers/mock_provider.py
Purpose: Simulated data provider for testing the performance feedback loop.
         Uses logarithmic decay to model realistic social media engagement.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timezone
from typing import Optional

from services.data_providers.base import DataProvider, PerformanceMetrics

class MockProvider(DataProvider):
    """Simulates platform metrics with realistic growth curves."""
    
    @property
    def platform_name(self) -> str:
        return "mock"

    def fetch_metrics(self, clip_id: str, since: Optional[datetime] = None) -> PerformanceMetrics:
        """
        Simulate engagement based on time since 'since' (or now).
        Model: Logarithmic growth that flattens after 72 hours.
        """
        # Determine "age" of the clip in hours (mocking it if since is missing)
        now = datetime.now(timezone.utc)
        start_time = since if since else now
        age_hours = (now - start_time).total_seconds() / 3600.0
        
        # Base volume: 100-500 views initially
        base_views = 250 + (random.randint(-50, 50))
        
        # Logarithmic growth: views = base * log2(age_hours + 2)
        # 1 hour -> base * 1.5
        # 24 hours -> base * 4.7
        # 72 hours -> base * 6.2
        multiplier = math.log2(max(1.0, age_hours) + 2.0)
        views = int(base_views * multiplier)
        
        # Derived metrics
        likes = int(views * 0.12)  # 12% like rate
        saves = int(views * 0.03)  # 3% save rate
        shares = int(views * 0.05) # 5% share rate
        comments = int(views * 0.01) # 1% comment rate
        
        # Calculate engagement score (Likes+Saves+Shares+Comments / Views)
        engagement_score = 0.0
        if views > 0:
            engagement_score = (likes + saves + shares + comments) / views

        return PerformanceMetrics(
            views=views,
            likes=likes,
            saves=saves,
            shares=shares,
            comments=comments,
            average_watch_time_seconds=15.5,
            completion_rate=0.65,
            engagement_score=round(engagement_score, 4)
        )

def get_mock_provider() -> MockProvider:
    return MockProvider()
