"""File: services/data_providers/base.py
Purpose: Abstract base class for platform-specific performance data retrieval.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class PerformanceMetrics:
    """Standardized engagement metrics across all platforms."""
    views: int = 0
    likes: int = 0
    saves: int = 0
    shares: int = 0
    comments: int = 0
    average_watch_time_seconds: Optional[float] = None
    completion_rate: Optional[float] = None
    engagement_score: float = 0.0


class DataProvider(ABC):
    """Abstract interface for fetching metrics from social platforms."""
    
    @abstractmethod
    def fetch_metrics(self, clip_id: str, since: Optional[datetime] = None) -> PerformanceMetrics:
        """Fetch the latest metrics for a specific clip ID."""
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the name of the platform (e.g., 'tiktok', 'youtube')."""
        pass
