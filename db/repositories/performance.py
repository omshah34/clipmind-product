"""Performance and Analytics repository functions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine
from db.repositories.jobs import get_job


def _row_to_mapping(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return dict(row)
    return dict(row)


def _ensure_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _build_top_clips(clips: list[Any] | None, limit: int = 5) -> list[dict[str, Any]]:
    if not clips:
        return []

    normalized: list[dict[str, Any]] = []
    for clip in clips:
        if hasattr(clip, "model_dump"):
            clip_data = clip.model_dump()
        elif hasattr(clip, "_mapping"):
            clip_data = dict(clip._mapping)
        elif isinstance(clip, dict):
            clip_data = dict(clip)
        else:
            clip_data = dict(vars(clip))
        normalized.append(clip_data)

    normalized.sort(key=lambda item: float(item.get("final_score") or 0), reverse=True)
    top_clips: list[dict[str, Any]] = []
    for clip in normalized[:limit]:
        top_clips.append(
            {
                "clip_index": int(clip.get("clip_index", 0)),
                "clip_url": clip.get("clip_url", ""),
                "duration": float(clip.get("duration", 0.0) or 0.0),
                "final_score": float(clip.get("final_score", 0.0) or 0.0),
                "reason": str(clip.get("reason", "")),
            }
        )
    return top_clips


def build_performance_summary(
    *,
    job_id: UUID | str,
    rows: list[Any],
    top_clips: list[Any] | None = None,
    latest_job_id: UUID | str | None = None,
    data_source: str | None = None,
) -> dict[str, Any]:
    """Build a dashboard-ready performance summary from clip rows."""
    normalized_rows = [_row_to_mapping(row) for row in rows]
    latest_job = str(latest_job_id or job_id)
    platforms = sorted({str(row.get("platform") or "unknown") for row in normalized_rows if row.get("platform")})
    total_jobs = len({str(row.get("job_id")) for row in normalized_rows if row.get("job_id")})

    totals = {
        "total_views": 0,
        "total_likes": 0,
        "total_saves": 0,
        "total_shares": 0,
        "total_comments": 0,
    }
    engagement_total = 0.0
    completion_total = 0.0
    completion_count = 0
    platform_buckets: dict[str, dict[str, Any]] = {}
    clip_points: list[dict[str, Any]] = []
    best_clip: dict[str, Any] | None = None
    worst_clip: dict[str, Any] | None = None
    synced_at: datetime | None = None
    detected_source = data_source or "mock"

    for row in normalized_rows:
        platform = str(row.get("platform") or "unknown")
        views = int(row.get("views") or 0)
        likes = int(row.get("likes") or 0)
        saves = int(row.get("saves") or 0)
        shares = int(row.get("shares") or 0)
        comments = int(row.get("comments") or 0)
        engagement = float(row.get("engagement_score") or 0.0)
        completion_rate = row.get("completion_rate")
        completion_rate_value = float(completion_rate) if completion_rate is not None else None
        predicted = float(row.get("ai_predicted_score") or 0.0)
        clip_index = int(row.get("clip_index") or 0)
        tier = row.get("milestone_tier")
        window_complete = bool(row.get("window_complete"))

        totals["total_views"] += views
        totals["total_likes"] += likes
        totals["total_saves"] += saves
        totals["total_shares"] += shares
        totals["total_comments"] += comments
        engagement_total += engagement
        if completion_rate_value is not None:
            completion_total += completion_rate_value
            completion_count += 1

        bucket = platform_buckets.setdefault(
            platform,
            {
                "platform": platform,
                "total_clips": 0,
                "total_views": 0,
                "total_likes": 0,
                "total_saves": 0,
                "total_shares": 0,
                "total_comments": 0,
                "engagement_total": 0.0,
                "completion_total": 0.0,
                "completion_count": 0,
                "best_performing_clip_index": None,
                "worst_performing_clip_index": None,
                "_best_score": None,
                "_worst_score": None,
            },
        )
        bucket["total_clips"] += 1
        bucket["total_views"] += views
        bucket["total_likes"] += likes
        bucket["total_saves"] += saves
        bucket["total_shares"] += shares
        bucket["total_comments"] += comments
        bucket["engagement_total"] += engagement
        if completion_rate_value is not None:
            bucket["completion_total"] += completion_rate_value
            bucket["completion_count"] += 1

        if bucket["_best_score"] is None or engagement > bucket["_best_score"]:
            bucket["_best_score"] = engagement
            bucket["best_performing_clip_index"] = clip_index
        if bucket["_worst_score"] is None or engagement < bucket["_worst_score"]:
            bucket["_worst_score"] = engagement
            bucket["worst_performing_clip_index"] = clip_index

        clip_points.append(
            {
                "clip_index": clip_index,
                "predicted": predicted,
                "actual": engagement,
                "tier": tier,
                "window_complete": window_complete,
            }
        )

        if best_clip is None or engagement > float(best_clip.get("engagement_score") or 0.0):
            best_clip = row
        if worst_clip is None or engagement < float(worst_clip.get("engagement_score") or 0.0):
            worst_clip = row

        row_synced_at = _ensure_datetime(row.get("synced_at")) or _ensure_datetime(row.get("updated_at")) or _ensure_datetime(row.get("created_at"))
        if row_synced_at and (synced_at is None or row_synced_at > synced_at):
            synced_at = row_synced_at

        if str(row.get("source_type") or "mock") == "real":
            detected_source = "real"

    platform_stats = []
    for bucket in platform_buckets.values():
        average_engagement = bucket["engagement_total"] / bucket["total_clips"] if bucket["total_clips"] else 0.0
        average_completion = bucket["completion_total"] / bucket["completion_count"] if bucket["completion_count"] else None
        platform_stats.append(
            {
                "platform": bucket["platform"],
                "total_clips": bucket["total_clips"],
                "total_views": bucket["total_views"],
                "total_likes": bucket["total_likes"],
                "total_saves": bucket["total_saves"],
                "total_shares": bucket["total_shares"],
                "total_comments": bucket["total_comments"],
                "average_engagement_score": round(float(average_engagement), 4),
                "average_completion_rate": round(float(average_completion), 4) if average_completion is not None else None,
                "best_performing_clip_index": bucket["best_performing_clip_index"],
                "worst_performing_clip_index": bucket["worst_performing_clip_index"],
            }
        )

    platform_stats.sort(key=lambda item: (item["total_views"], item["average_engagement_score"]), reverse=True)
    top_platform = platform_stats[0]["platform"] if platform_stats else "unknown"
    overall_engagement = engagement_total / len(normalized_rows) if normalized_rows else 0.0
    average_completion_rate = completion_total / completion_count if completion_count else None
    top_clips_payload = _build_top_clips(top_clips)
    if not top_clips_payload and best_clip is not None:
        top_clips_payload = _build_top_clips([best_clip])

    return {
        "job_id": latest_job,
        "total_clips": len(normalized_rows),
        "platforms": platforms,
        "total_views": totals["total_views"],
        "total_likes": totals["total_likes"],
        "total_saves": totals["total_saves"],
        "total_shares": totals["total_shares"],
        "total_comments": totals["total_comments"],
        "overall_engagement_score": round(float(overall_engagement), 4),
        "average_completion_rate": round(float(average_completion_rate), 4) if average_completion_rate is not None else None,
        "platform_stats": platform_stats,
        "top_platform": top_platform,
        "best_clip_index": int(best_clip.get("clip_index", 0)) if best_clip else 0,
        "worst_clip_index": int(worst_clip.get("clip_index", 0)) if worst_clip else 0,
        "synced_at": synced_at or datetime.now(timezone.utc),
        "latest_job_id": latest_job,
        "top_clips": top_clips_payload,
        "all_clips_performance": clip_points,
        "data_source": detected_source,
        "total_jobs": total_jobs,
    }


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
    published_date: datetime | None = None,
) -> dict[str, Any]:
    """Insert or update performance metrics for a specific clip."""
    if synced_at is None:
        synced_at = datetime.now(timezone.utc)
        
    query = text("""
        INSERT INTO clip_performance (
            user_id, job_id, clip_index, platform, source_type,
            views, likes, engagement_score, performance_delta,
            milestone_tier, window_complete, synced_at, ai_predicted_score, published_date
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :source_type,
            :views, :likes, :engagement_score, :performance_delta,
            :milestone_tier, :window_complete, :synced_at, :ai_predicted_score, :published_date
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
            published_date = COALESCE(EXCLUDED.published_date, clip_performance.published_date),
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
            "ai_predicted_score": ai_predicted_score,
            "published_date": published_date,
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
        ids = alert_ids if isinstance(alert_ids, list) else [alert_ids]
        placeholders = ", ".join(f":id_{idx}" for idx in range(len(ids)))
        query = text(f"""
            UPDATE performance_alerts SET is_read = TRUE
            WHERE user_id = :user_id AND id IN ({placeholders})
        """)
        params = {"user_id": str(user_id)}
        params.update({f"id_{idx}": alert_id for idx, alert_id in enumerate(ids)})
        
    with engine.begin() as connection:
        result = connection.execute(query, params)
        return result.rowcount


def get_job_performance_summary(user_id: UUID | str, job_id: UUID | str) -> dict[str, Any] | None:
    """Return a dashboard-ready summary for a single job."""
    job = get_job(job_id)
    if job is None:
        return None
    if job.user_id and str(job.user_id) != str(user_id):
        return None

    query = text(
        """
        SELECT *
        FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id
        ORDER BY synced_at DESC, created_at DESC, clip_index ASC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "job_id": str(job_id)}).fetchall()

    data_source = "mock"
    for row in rows:
        if getattr(row, "source_type", None) == "real":
            data_source = "real"
            break

    return build_performance_summary(
        job_id=str(job.id),
        rows=rows,
        top_clips=getattr(job, "clips_json", None),
        latest_job_id=str(job.id),
        data_source=data_source,
    )
