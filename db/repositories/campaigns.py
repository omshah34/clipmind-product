"""Campaign repository functions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def _row_to_campaign_record(row: Any) -> dict[str, Any]:
    """Convert database row to campaign dict."""
    data = dict(row._mapping)
    if isinstance(data.get("schedule_config"), str):
        try:
            data["schedule_config"] = json.loads(data["schedule_config"])
        except json.JSONDecodeError:
            data["schedule_config"] = {}
    return data


def create_campaign(
    user_id: UUID | str,
    name: str,
    description: str | None = None,
    schedule_config: dict | None = None,
) -> dict[str, Any]:
    """Create a new campaign."""
    if schedule_config is None:
        schedule_config = {
            "publish_interval_days": 1,
            "publish_hour": 9,
            "publish_timezone": "UTC",
        }
    
    query = text(
        """
        INSERT INTO campaigns (user_id, name, description, schedule_config)
        VALUES (:user_id, :name, :description, :schedule_config)
        RETURNING *
        """
    )
    params = {
        "user_id": str(user_id),
        "name": name,
        "description": description,
        "schedule_config": json.dumps(schedule_config),
    }
    with engine.begin() as connection:
        row = connection.execute(query, params).one()
    return _row_to_campaign_record(row)


def get_campaign(campaign_id: UUID | str) -> dict[str, Any] | None:
    """Get a single campaign by ID."""
    query = text(
        """
        SELECT id, user_id, name, description, schedule_config, status, created_at, updated_at
        FROM campaigns WHERE id = :campaign_id
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"campaign_id": str(campaign_id)}).one_or_none()
    return _row_to_campaign_record(row) if row else None


def list_campaigns(
    user_id: UUID | str,
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """List campaigns for a user."""
    status_filter = "AND status = :status" if status else ""
    
    count_query = text(
        f"""
        SELECT COUNT(*) FROM campaigns
        WHERE user_id = :user_id {status_filter}
        """
    )
    list_query = text(
        f"""
        SELECT id, user_id, name, description, schedule_config, status, created_at, updated_at
        FROM campaigns
        WHERE user_id = :user_id {status_filter}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    params = {"user_id": str(user_id), "limit": limit, "offset": offset}
    if status:
        params["status"] = status
    
    with engine.connect() as connection:
        total = connection.execute(count_query, params).scalar()
        rows = connection.execute(list_query, params).all()
    
    campaigns = [_row_to_campaign_record(row) for row in rows]
    return campaigns, total


def update_campaign(
    campaign_id: UUID | str,
    **updates: Any,
) -> dict[str, Any] | None:
    """Update campaign fields."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return None
    
    allowed_fields = {"name", "description", "schedule_config", "status"}
    updates = {k: v for k, v in updates.items() if k in allowed_fields and v is not None}
    
    if not updates:
        return campaign
    
    assignments = []
    params = {"campaign_id": str(campaign_id)}
    
    for field, value in updates.items():
        if field == "schedule_config" and isinstance(value, dict):
            assignments.append(f"{field} = :{field}")
            params[field] = json.dumps(value)
        else:
            assignments.append(f"{field} = :{field}")
            params[field] = value
    
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    
    query = text(
        f"""
        UPDATE campaigns
        SET {", ".join(assignments)}
        WHERE id = :campaign_id
        RETURNING *
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, params).one()
    return _row_to_campaign_record(row)


def delete_campaign(campaign_id: UUID | str) -> bool:
    """Delete a campaign and unlink associated jobs."""
    query_unlink = text(
        """
        UPDATE jobs SET campaign_id = NULL WHERE campaign_id = :campaign_id
        """
    )
    query_delete = text(
        """
        DELETE FROM campaigns WHERE id = :campaign_id
        """
    )
    
    with engine.begin() as connection:
        connection.execute(query_unlink, {"campaign_id": str(campaign_id)})
        result = connection.execute(query_delete, {"campaign_id": str(campaign_id)})
    
    return result.rowcount > 0


def get_campaign_clips(campaign_id: UUID | str) -> list[dict[str, Any]]:
    """Get all clips associated with a campaign."""
    query = text(
        """
        SELECT j.id as job_id, c.*, j.scheduled_publish_date
        FROM jobs j
        JOIN LATERAL (SELECT json_to_recordset(clips_json) AS 
            (clip_index int, start_time float, end_time float, duration float, 
             final_score float, reason text, hook_score float, emotion_score float,
             clarity_score float, story_score float, virality_score float)) c ON true
        WHERE j.campaign_id = :campaign_id AND j.clips_json IS NOT NULL
        ORDER BY j.created_at DESC, c.clip_index
        """
    )
    
    with engine.connect() as connection:
        rows = connection.execute(query, {"campaign_id": str(campaign_id)}).all()
    
    return [dict(row._mapping) for row in rows]


def schedule_clips_for_campaign(
    campaign_id: UUID | str,
    publish_dates: dict[str, list[str]],
) -> int:
    """Schedule clips from specific jobs in a campaign."""
    campaign = get_campaign(campaign_id)
    if not campaign:
        return 0
    
    schedule_config = campaign.get("schedule_config", {})
    interval_days = schedule_config.get("publish_interval_days", 1)
    
    scheduled_count = 0
    current_date = datetime.now()
    
    for job_id_str, clip_indices in publish_dates.items():
        for idx, clip_idx in enumerate(clip_indices):
            publish_date = current_date + timedelta(days=idx * interval_days)
            
            query = text(
                """
                UPDATE jobs
                SET scheduled_publish_date = :publish_date
                WHERE id = :job_id AND campaign_id = :campaign_id
                """
            )
            
            with engine.begin() as connection:
                result = connection.execute(
                    query,
                    {
                        "publish_date": publish_date,
                        "job_id": str(job_id_str),
                        "campaign_id": str(campaign_id),
                    },
                )
                if result.rowcount > 0:
                    scheduled_count += 1
    
    return scheduled_count
