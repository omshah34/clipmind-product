"""Performance and Analytics repository functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def upsert_clip_performance(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
    source_type: str = "real",
    views: int = 0,
    likes: int = 0,
    engagement_score: float = 0.0,
    performance_delta: float = 0.0,
    milestone_tier: str | None = None,
    window_complete: bool = False,
    synced_at: datetime | None = None,
    ai_predicted_score: float | None = None,
) -> dict[str, Any]:
    """Insert or update performance metrics for a specific clip."""
    if synced_at is None:
        synced_at = datetime.now(timezone.utc)
        
    query = text("""
        INSERT INTO clip_performance (
            user_id, job_id, clip_index, platform, source_type,
            views, likes, engagement_score, performance_delta,
            milestone_tier, window_complete, synced_at, ai_predicted_score
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :source_type,
            :views, :likes, :engagement_score, :performance_delta,
            :milestone_tier, :window_complete, :synced_at, :ai_predicted_score
        )
        ON CONFLICT (user_id, job_id, clip_index, platform) DO UPDATE SET
            views = EXCLUDED.views,
            likes = EXCLUDED.likes,
            engagement_score = EXCLUDED.engagement_score,
            performance_delta = EXCLUDED.performance_delta,
            milestone_tier = EXCLUDED.milestone_tier,
            window_complete = EXCLUDED.window_complete,
            synced_at = EXCLUDED.synced_at,
            ai_predicted_score = COALESCE(EXCLUDED.ai_predicted_score, clip_performance.ai_predicted_score),
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "platform": platform,
            "source_type": source_type,
            "views": views,
            "likes": likes,
            "engagement_score": engagement_score,
            "performance_delta": performance_delta,
            "milestone_tier": milestone_tier,
            "window_complete": window_complete,
            "synced_at": synced_at,
            "ai_predicted_score": ai_predicted_score
        }).one()
    return dict(row._mapping)


def create_performance_alert(
    user_id: UUID | str,
    alert_type: str,
    message: str,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Create a new performance milestone or alert with 24h cooldown."""
    # Cooldown check logic
    check_query = text("""
        SELECT last_alerted_at FROM alert_cooldowns
        WHERE user_id = :user_id AND alert_type = :alert_type
    """)
    
    with engine.begin() as connection:
        last_alert = connection.execute(check_query, {
            "user_id": str(user_id), 
            "alert_type": alert_type
        }).scalar()
        
        if last_alert:
            now = datetime.now(timezone.utc)
            # SQLite returns strings; PostgreSQL returns datetime objects
            if isinstance(last_alert, str):
                from datetime import datetime as dt_cls
                try:
                    last_alert = dt_cls.fromisoformat(last_alert).replace(tzinfo=timezone.utc)
                except ValueError:
                    last_alert = dt_cls.strptime(last_alert, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            elif last_alert.tzinfo is None:
                last_alert = last_alert.replace(tzinfo=timezone.utc)
            
            if (now - last_alert).total_seconds() < 86400: # 24h
                return {}

        query = text("""
            INSERT INTO performance_alerts (user_id, alert_type, message, metadata_json)
            VALUES (:user_id, :alert_type, :message, :metadata)
            RETURNING *
        """)
        row = connection.execute(query, {
            "user_id": str(user_id),
            "alert_type": alert_type,
            "message": message,
            "metadata": json.dumps(metadata or {})
        }).fetchone()
        
        # Update cooldown
        connection.execute(text("""
            INSERT INTO alert_cooldowns (user_id, alert_type, last_alerted_at)
            VALUES (:user_id, :alert_type, CURRENT_TIMESTAMP)
            ON CONFLICT (user_id, alert_type) DO UPDATE SET last_alerted_at = CURRENT_TIMESTAMP
        """), {"user_id": str(user_id), "alert_type": alert_type})
        
    return dict(row._mapping) if row else {}


def list_performance_alerts(user_id: UUID | str, limit: int = 10, unread_only: bool = False) -> list[dict[str, Any]]:
    """Retrieve recent milestone and error alerts."""
    filter_unread = " AND is_read = FALSE" if unread_only else ""
    query = text(f"""
        SELECT * FROM performance_alerts
        WHERE user_id = :user_id {filter_unread}
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "limit": limit}).fetchall()
    
    results = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("metadata_json"), str):
            try:
                d["metadata"] = json.loads(d["metadata_json"])
            except json.JSONDecodeError:
                d["metadata"] = {}
        results.append(d)
    return results


def mark_alerts_as_read(user_id: str | UUID, alert_ids: list[str] | str = "all") -> int:
    """Mark alerts as read."""
    if alert_ids == "all":
        query = text("""
            UPDATE performance_alerts SET is_read = TRUE
            WHERE user_id = :user_id AND is_read = FALSE
        """)
        params = {"user_id": str(user_id)}
    else:
        query = text("""
            UPDATE performance_alerts SET is_read = TRUE
            WHERE user_id = :user_id AND id = ANY(:ids)
        """)
        params = {"user_id": str(user_id), "ids": alert_ids if isinstance(alert_ids, list) else [alert_ids]}
        
    with engine.begin() as connection:
        result = connection.execute(query, params)
        return result.rowcount
