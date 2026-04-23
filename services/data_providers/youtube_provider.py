"""File: services/data_providers/youtube_provider.py
Purpose: Real YouTube Data API integration for performance metrics.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

from services.data_providers.base import DataProvider, PerformanceMetrics
from services.data_providers.encryption import SecretManager
from db.repositories.users import get_platform_credentials, save_platform_credentials
from core.config import settings

logger = logging.getLogger(__name__)

class PlatformQuotaError(Exception):
    """Raised when the platform API quota is exhausted."""
    pass

class YoutubeProvider(DataProvider):
    """Real YouTube metrics retrieval using Data API v3."""
    
    @property
    def platform_name(self) -> str:
        return "youtube"

    def fetch_metrics(self, clip_id: str, since: Optional[datetime] = None) -> PerformanceMetrics:
        """
        Fetch latest statistics for a YouTube video.
        Uses decypted OAuth tokens and handles JIT refresh.
        """
        # Note: clip_id here is the platform-specific ID (YouTube video ID)
        # In a real flow, this is stored in platform_clip_id column
        
        # 1. Get credentials for user (user_id needs to be passed in or contextually available)
        # For simplicity in this provider call, we assume clip_id might be "user_id:video_id"
        # but better is to pass user_id to fetch_metrics. 
        # REFACTOR: Updating base DataProvider or using a context?
        # Let's assume the caller provides a pre-initialized provider or we find it.
        pass

    def fetch_metrics_for_user(self, user_id: str, video_id: str) -> PerformanceMetrics:
        """Fetch metrics using a specific user's credentials."""
        creds = self._get_user_credentials(user_id)
        if not creds:
            logger.warning("[youtube] No credentials found for user %s", user_id)
            return PerformanceMetrics()

        try:
            youtube = build("youtube", "v3", credentials=creds)
            request = youtube.videos().list(
                part="statistics",
                id=video_id
            )
            response = request.execute()
            
            if not response.get("items"):
                logger.warning("[youtube] No video found for ID %s", video_id)
                return PerformanceMetrics()

            stats = response["items"][0]["statistics"]
            
            # Map YouTube v3 stats to ClipMind PerformanceMetrics
            metrics = PerformanceMetrics(
                views=int(stats.get("viewCount", 0)),
                likes=int(stats.get("likeCount", 0)),
                comments=int(stats.get("commentCount", 0)),
                # YouTube v3 public statistics don't include shares/saves 
                # (Requires YouTube Reporting API or specific Analytics scopes)
                shares=0,
                saves=0
            )
            
            # Calculate a basic engagement score
            if metrics.views > 0:
                metrics.engagement_score = (metrics.likes + metrics.comments) / metrics.views
            
            return metrics

        except Exception as e:
            if "quotaExceeded" in str(e):
                logger.error("[youtube] Quota exceeded for user %s", user_id)
                raise PlatformQuotaError("YouTube API quota reached.")
            logger.error("[youtube] Failed to fetch metrics: %s", e)
            raise

    def _get_user_credentials(self, user_id: str) -> Optional[Credentials]:
        """Retrieve, decrypt, and refresh YouTube OAuth credentials."""
        db_creds = get_platform_credentials(user_id, "youtube")
        if not db_creds:
            return None

        # Decrypt tokens
        access_token = SecretManager.decrypt(db_creds.get("access_token_encrypted"))
        refresh_token = SecretManager.decrypt(db_creds.get("refresh_token_encrypted"))
        
        scopes = db_creds.get("scopes", "").split(",") if db_creds.get("scopes") else []

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.youtube_client_id,
            client_secret=settings.youtube_client_secret,
            scopes=scopes
        )

        # JIT Refresh
        if creds.expired or (creds.expiry and creds.expiry < datetime.now(timezone.utc) + timedelta(minutes=5)):
            logger.info("[youtube] Refreshing token for user %s", user_id)
            try:
                creds.refresh(Request())
                # Save new token back to DB
                save_platform_credentials(
                    user_id=user_id,
                    platform="youtube",
                    access_token_encrypted=SecretManager.encrypt(creds.token),
                    refresh_token_encrypted=db_creds.get("refresh_token_encrypted"), # Keep old refresh
                    expires_at=creds.expiry,
                    account_id=db_creds.get("account_id"),
                    account_name=db_creds.get("account_name"),
                    scopes=scopes
                )
            except Exception as e:
                logger.error("[youtube] Token refresh failed: %s", e)
                return None

        return creds

def get_youtube_provider() -> YoutubeProvider:
    return YoutubeProvider()
