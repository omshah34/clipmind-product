"""File: services/performance_engine.py
Purpose: Orchestrates the performance feedback loop (The "Infinite Loop").
         Calculates deltas, detects milestones, and triggers DNA updates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from db.queries import (
    upsert_clip_performance,
    create_performance_alert,
    get_platform_credentials,
    engine,
)
from sqlalchemy import text

from services.data_providers.base import DataProvider
from services.content_dna import apply_performance_feedback

logger = logging.getLogger(__name__)

# --- Configuration & Milestones ---
SYNC_COOLDOWN_MINUTES = 15

# Milestones defined by % improvement over prediction
MILESTONES = {
    "viral": 1.0,     # >100% better
    "validated": 0.3, # >30% better
    "emerging": 0.1,  # >10% better
}

class PerformanceEngine:
    def __init__(self) -> None:
        """Engine resolves providers dynamically based on user credentials."""
        pass

    def sync_user_performance(self, user_id: str | UUID) -> dict[str, Any]:
        """Sync metrics for all published clips across all connected platforms."""
        # 1. Rate limiting
        if not self.can_sync(user_id):
            return {"status": "error", "message": f"Rate limit: Please wait {SYNC_COOLDOWN_MINUTES} minutes."}

        # 2. Identify active platforms for this user
        with engine.connect() as connection:
            platforms_res = connection.execute(
                text("SELECT platform FROM platform_credentials WHERE user_id = :u AND is_active = TRUE"),
                {"u": str(user_id)}
            ).fetchall()
        
        active_platforms = [p[0] for p in platforms_res]
        
        # 3. Fetch clips needing sync (those whose feedback window isn't yet complete)
        query = text("""
            SELECT job_id, clip_index, platform, platform_clip_id, ai_predicted_score
            FROM clip_performance
            WHERE user_id = :user_id AND window_complete = FALSE
        """)
        
        with engine.connect() as connection:
            clips = connection.execute(query, {"user_id": str(user_id)}).fetchall()

        results = {"processed": 0, "milestones": 0, "errors": 0, "platforms": active_platforms}

        for clip in clips:
            # Resolve provider (YouTube, TikTok, or Mock)
            provider = self._get_provider_for_user(user_id, clip.platform)
            
            try:
                self.sync_clip_performance(
                    user_id=user_id,
                    job_id=clip.job_id,
                    clip_index=clip.clip_index,
                    platform=clip.platform,
                    platform_clip_id=clip.platform_clip_id,
                    predicted_score=clip.ai_predicted_score,
                    provider=provider
                )
                results["processed"] += 1
            except Exception as exc:
                logger.error("[perf] Failed sync for %s:%s: %s", clip.job_id, clip.clip_index, exc)
                results["errors"] += 1

        return results

    def sync_clip_performance(
        self, 
        user_id: str | UUID, 
        job_id: str, 
        clip_index: int, 
        platform: str,
        platform_clip_id: str | None,
        predicted_score: float,
        provider: DataProvider
    ) -> dict[str, Any]:
        """Sync a single clip using the resolved provider and trigger feedback loops."""
        try:
            # 1. Fetch metrics from platform
            if hasattr(provider, "fetch_metrics_for_user") and platform_clip_id:
                metrics = provider.fetch_metrics_for_user(str(user_id), platform_clip_id)
            else:
                metrics = provider.fetch_metrics(platform_clip_id or f"{job_id}_{clip_index}")
            
            # 2. Calculate Delta and Milestone
            actual_score = metrics.engagement_score
            delta = actual_score - predicted_score
            
            milestone = None
            if predicted_score > 0:
                percentage_gain = delta / predicted_score
                if percentage_gain >= MILESTONES["viral"]: milestone = "viral"
                elif percentage_gain >= MILESTONES["validated"]: milestone = "validated"
                elif percentage_gain >= MILESTONES["emerging"]: milestone = "emerging"

            # 3. Persistence: Update the feedback record
            # window_complete is True if we've reached a significant view threshold (e.g. 100 views)
            # or a time threshold (handled by the caller or provider)
            window_complete = metrics.views >= 100 
            perf = upsert_clip_performance(
                user_id=str(user_id), 
                job_id=job_id, 
                clip_index=clip_index,
                platform=platform, 
                source_type=provider.platform_name,
                views=metrics.views, 
                likes=metrics.likes,
                engagement_score=metrics.engagement_score,
                performance_delta=delta, 
                milestone_tier=milestone,
                window_complete=window_complete,
                synced_at=datetime.now(timezone.utc)
            )

            # 4. Global Intelligence Alerts: User visibility for wins
            if milestone in ["viral", "validated"]:
                create_performance_alert(
                    user_id=str(user_id), 
                    alert_type="milestone",
                    message=f"Milestone! Clip {clip_index} reached '{milestone.capitalize()}' on {platform.capitalize()}.",
                    metadata={"job_id": job_id, "clip_index": clip_index, "tier": milestone, "delta": delta}
                )

            # 5. DNA Feedback Loop: Close the loop for future scoring
            if metrics.views > 0:
                apply_performance_feedback(
                    user_id=str(user_id), 
                    job_id=job_id, 
                    clip_index=clip_index,
                    delta=delta, 
                    milestone_tier=milestone
                )

            return perf

        except Exception as e:
            # Handle standard Auth failures
            err_msg = str(e)
            if "quota" in err_msg.lower():
                logger.error("[perf] Quota hit for platform %s", platform)
            elif any(x in err_msg.lower() for x in ["401", "invalid_grant", "revoked", "invalid_token"]):
                logger.warning("[perf] Credentials revoked for %s. Marking inactive.", platform)
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE platform_credentials SET is_active = FALSE, last_error = :err WHERE user_id = :u AND platform = :p"),
                        {"err": err_msg, "u": str(user_id), "p": platform}
                    )
                create_performance_alert(
                    user_id=str(user_id), alert_type="sync_error",
                    message=f"Action Required: Your {platform.capitalize()} connection has expired or been revoked. Please reconnect to continue syncing performance.",
                    metadata={"platform": platform, "error": err_msg}
                )
            raise

    def _get_provider_for_user(self, user_id: str | UUID, platform: str) -> DataProvider:
        """Resolve the best provider for a platform. Defaults to Mock if no credentials."""
        from services.data_providers.youtube_provider import get_youtube_provider
        from services.data_providers.tiktok_provider import get_tiktok_provider
        from services.data_providers.mock_provider import get_mock_provider

        creds = get_platform_credentials(str(user_id), platform)
        if creds and creds.get("is_active"):
            if platform == "youtube": return get_youtube_provider()
            if platform == "tiktok": return get_tiktok_provider()
        
        return get_mock_provider()

    def can_sync(self, user_id: str | UUID) -> bool:
        """Rate limit syncs to preserve platform quotas and user experience."""
        query = text("SELECT MAX(synced_at) FROM clip_performance WHERE user_id = :u")
        with engine.connect() as conn:
            last = conn.execute(query, {"u": str(user_id)}).scalar()
        
        if not last: 
            return True
        
        # Ensure 'last' is timezone-aware for comparison
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
            
        return (datetime.now(timezone.utc) - last) >= timedelta(minutes=SYNC_COOLDOWN_MINUTES)

def get_performance_engine() -> PerformanceEngine:
    return PerformanceEngine()
