"""File: services/data_providers/tiktok_provider.py
Purpose: TikTok performance metrics retrieval (via unofficial scraper).
"""

from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

# Using the unofficial TikTokApi wrapper
# pip install TikTokApi
from TikTokApi import TikTokApi

from services.data_providers.base import DataProvider, PerformanceMetrics
from core.config import settings

logger = logging.getLogger(__name__)

class TikTokProvider(DataProvider):
    """TikTok metrics retrieval using unofficial scraping."""
    
    @property
    def platform_name(self) -> str:
        return "tiktok"

    def fetch_metrics(self, clip_id: str, since: Optional[datetime] = None) -> PerformanceMetrics:
        """
        Fetch latest statistics for a TikTok video.
        Uses the unofficial TikTokApi scraper.
        """
        # clip_id expected to be the TikTok video ID
        
        session_id = settings.tiktok_session_id
        if not session_id or session_id == "your_tiktok_session_id":
            logger.warning("[tiktok] No TIKTOK_SESSION_ID provided. Falling back to empty metrics.")
            return PerformanceMetrics()

        try:
            # Note: TikTokApi v6+ often requires playwright or specific setup
            # This implementation assumes the environment is configured correctly.
            with TikTokApi() as api:
                video = api.video(id=clip_id)
                data = video.info_full()
                
                stats = data.get("stats", {})
                
                metrics = PerformanceMetrics(
                    views=int(stats.get("playCount", 0)),
                    likes=int(stats.get("diggCount", 0)),
                    shares=int(stats.get("shareCount", 0)),
                    comments=int(stats.get("commentCount", 0)),
                    saves=int(stats.get("collectCount", 0)),
                )
                
                # Calculate engagement score
                total_engagement = metrics.likes + metrics.comments + metrics.shares + metrics.saves
                if metrics.views > 0:
                    metrics.engagement_score = total_engagement / metrics.views
                    
                return metrics

        except Exception as e:
            logger.error("[tiktok] Failed to scrape metrics for %s: %s", clip_id, e)
            # Unofficial APIs are unstable; we log and return partial data or raise
            return PerformanceMetrics()

def get_tiktok_provider() -> TikTokProvider:
    return TikTokProvider()
