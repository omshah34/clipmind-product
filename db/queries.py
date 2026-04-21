"""File: db/queries.py
Purpose: All database queries for the jobs table. Single source of truth
         for all database operations. No inline SQL appears in routes, workers,
         or services.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from api.models.job import JobRecord
from api.models.brand_kit import BrandKitRecord
from db.connection import engine
from db.job_state import record_job_transition


JSON_FIELDS = {"transcript_json", "clips_json", "timeline_json"}
UPDATABLE_FIELDS = {
    "status",
    "source_video_url",
    "audio_url",
    "transcript_json",
    "clips_json",
    "timeline_json",
    "failed_stage",
    "error_message",
    "retry_count",
    "prompt_version",
    "estimated_cost_usd",
    "actual_cost_usd",
    "language",
    "campaign_id",
    "scheduled_publish_date",
}


def _row_to_job_record(row: Any) -> JobRecord:
    data = dict(row._mapping)
    for field in JSON_FIELDS:
        if isinstance(data.get(field), str):
            try:
                data[field] = json.loads(data[field])
            except json.JSONDecodeError:
                pass
    return JobRecord.model_validate(data)


def create_job(
    *,
    source_video_url: str,
    prompt_version: str,
    estimated_cost_usd: float,
    user_id: UUID | str | None = None,
    brand_kit_id: UUID | str | None = None,
    status: str | None = None,
    language: str | None = "en",
) -> JobRecord:
    columns = [
        "source_video_url",
        "prompt_version",
        "estimated_cost_usd",
        "user_id",
        "brand_kit_id",
        "language",
    ]
    values = [
        ":source_video_url",
        ":prompt_version",
        ":estimated_cost_usd",
        ":user_id",
        ":brand_kit_id",
        ":language",
    ]
    if status is not None:
        columns.insert(0, "status")
        values.insert(0, ":status")

    query = text(
        f"""
        INSERT INTO jobs (
            {", ".join(columns)}
        )
        VALUES (
            {", ".join(values)}
        )
        RETURNING *
        """
    )
    with engine.begin() as connection:
        params = {
            "source_video_url": source_video_url,
            "prompt_version": prompt_version,
            "estimated_cost_usd": estimated_cost_usd,
            "user_id": str(user_id) if user_id else None,
            "brand_kit_id": str(brand_kit_id) if brand_kit_id else None,
            "language": language or "en",
        }
        if status is not None:
            params["status"] = status
        row = connection.execute(query, params).one()
    return _row_to_job_record(row)


def get_job(job_id: UUID | str) -> JobRecord | None:
    query = text("SELECT * FROM jobs WHERE id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": str(job_id)}).one_or_none()
    return _row_to_job_record(row) if row else None


def update_job(job_id: UUID | str, **fields: Any) -> JobRecord:
    current = get_job(job_id)
    previous_status = current.status if current else None
    assignments: list[str] = []
    params: dict[str, Any] = {"job_id": str(job_id)}

    for field_name, value in fields.items():
        if field_name not in UPDATABLE_FIELDS:
            raise ValueError(f"Unsupported job field: {field_name}")
        if field_name in JSON_FIELDS:
            assignments.append(f"{field_name} = :{field_name}")
            params[field_name] = json.dumps(value) if value is not None else None
        else:
            assignments.append(f"{field_name} = :{field_name}")
            params[field_name] = value

    if not assignments:
        job = get_job(job_id)
        if job is None:
            raise ValueError("Job not found")
        return job

    query = text(
        f"""
        UPDATE jobs
        SET {", ".join(assignments)}
        WHERE id = :job_id
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(query, params).one()
    updated = _row_to_job_record(row)
    if updated.status != previous_status:
        record_job_transition(
            str(job_id),
            previous_status,
            updated.status,
            stage=fields.get("status"),
            payload={key: value for key, value in fields.items() if key != "status"},
        )
    return updated


# ---------------------------------------------------------------------------
# Brand Kit Queries
# ---------------------------------------------------------------------------

def _row_to_brand_kit_record(row: Any) -> BrandKitRecord:
    return BrandKitRecord.model_validate(dict(row._mapping))


def create_brand_kit(
    *,
    user_id: UUID | str,
    name: str,
    font_name: str = "Arial",
    font_size: int = 22,
    bold: bool = True,
    alignment: int = 2,
    primary_colour: str = "&H00FFFFFF",
    outline_colour: str = "&H00000000",
    outline: int = 2,
    watermark_url: str | None = None,
    intro_clip_url: str | None = None,
    outro_clip_url: str | None = None,
    is_default: bool = False,
) -> BrandKitRecord:
    """Create a new brand kit for a user."""
    query = text(
        """
        INSERT INTO brand_kits (
            user_id, name, font_name, font_size, bold, alignment,
            primary_colour, outline_colour, outline,
            watermark_url, intro_clip_url, outro_clip_url, is_default
        )
        VALUES (
            :user_id, :name, :font_name, :font_size, :bold, :alignment,
            :primary_colour, :outline_colour, :outline,
            :watermark_url, :intro_clip_url, :outro_clip_url, :is_default
        )
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "font_name": font_name,
                "font_size": font_size,
                "bold": bold,
                "alignment": alignment,
                "primary_colour": primary_colour,
                "outline_colour": outline_colour,
                "outline": outline,
                "watermark_url": watermark_url,
                "intro_clip_url": intro_clip_url,
                "outro_clip_url": outro_clip_url,
                "is_default": is_default,
            },
        ).one()
    return _row_to_brand_kit_record(row)


def get_brand_kit(brand_kit_id: UUID | str) -> BrandKitRecord | None:
    """Retrieve a brand kit by ID."""
    query = text("SELECT * FROM brand_kits WHERE id = :brand_kit_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"brand_kit_id": str(brand_kit_id)}).one_or_none()
    return _row_to_brand_kit_record(row) if row else None


def get_user_brand_kits(user_id: UUID | str) -> list[BrandKitRecord]:
    """Retrieve all brand kits for a user."""
    query = text(
        """
        SELECT * FROM brand_kits WHERE user_id = :user_id
        ORDER BY is_default DESC, created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    return [_row_to_brand_kit_record(row) for row in rows]


def get_user_default_brand_kit(user_id: UUID | str) -> BrandKitRecord | None:
    """Retrieve the default brand kit for a user."""
    query = text(
        """
        SELECT * FROM brand_kits WHERE user_id = :user_id AND is_default = true
        LIMIT 1
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()
    return _row_to_brand_kit_record(row) if row else None


def update_brand_kit(brand_kit_id: UUID | str, **fields: Any) -> BrandKitRecord:
    """Update a brand kit. Only provided fields are updated."""
    brand_kit = get_brand_kit(brand_kit_id)
    if not brand_kit:
        raise ValueError(f"Brand kit {brand_kit_id} not found")

    # List of updatable fields in brand_kits table
    updatable_fields = {
        "name",
        "font_name",
        "font_size",
        "bold",
        "alignment",
        "primary_colour",
        "outline_colour",
        "outline",
        "watermark_url",
        "intro_clip_url",
        "outro_clip_url",
        "is_default",
    }

    assignments: list[str] = []
    params: dict[str, Any] = {"brand_kit_id": str(brand_kit_id)}

    for field_name, value in fields.items():
        if field_name not in updatable_fields:
            raise ValueError(f"Cannot update field: {field_name}")
        assignments.append(f"{field_name} = :{field_name}")
        params[field_name] = value

    if not assignments:
        return brand_kit

    query = text(
        f"""
        UPDATE brand_kits
        SET {", ".join(assignments)}
        WHERE id = :brand_kit_id
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(query, params).one()
    return _row_to_brand_kit_record(row)


def delete_brand_kit(brand_kit_id: UUID | str) -> bool:
    """Delete a brand kit and clear any jobs that reference it."""
    query_clear = text(
        """
        UPDATE jobs SET brand_kit_id = NULL WHERE brand_kit_id = :brand_kit_id
        """
    )
    query_delete = text(
        """
        DELETE FROM brand_kits WHERE id = :brand_kit_id
        """
    )
    with engine.begin() as connection:
        connection.execute(query_clear, {"brand_kit_id": str(brand_kit_id)})
        result = connection.execute(query_delete, {"brand_kit_id": str(brand_kit_id)})
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Timeline / Clip Studio Queries
# ---------------------------------------------------------------------------

def get_job_timeline(job_id: UUID | str) -> dict | None:
    """Retrieve timeline_json for a job (may be None)."""
    query = text("SELECT timeline_json FROM jobs WHERE id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": str(job_id)}).one_or_none()
    return row[0] if row else None


def update_job_timeline(job_id: UUID | str, timeline_data: dict) -> JobRecord:
    """Update or create timeline_json for a job."""
    return update_job(job_id, timeline_json=timeline_data)


def append_regeneration_result(job_id: UUID | str, result: dict) -> dict:
    """Append a regeneration result to the timeline_json array."""
    current_timeline = get_job_timeline(job_id)
    
    if current_timeline is None:
        current_timeline = {"clips": [], "regeneration_results": []}
    
    if "regeneration_results" not in current_timeline:
        current_timeline["regeneration_results"] = []
    
    current_timeline["regeneration_results"].append(result)
    
    update_job_timeline(job_id, current_timeline)
    return current_timeline


# ---------------------------------------------------------------------------
# Campaign Queries
# ---------------------------------------------------------------------------

def _row_to_campaign_record(row: Any) -> dict:
    """Convert database row to campaign dict."""
    data = dict(row._mapping)
    if isinstance(data.get("schedule_config"), str):
        try:
            data["schedule_config"] = json.loads(data["schedule_config"])
        except json.JSONDecodeError:
            pass
    return data


def create_campaign(
    user_id: UUID | str,
    name: str,
    description: str | None = None,
    schedule_config: dict | None = None,
) -> dict:
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


def get_campaign(campaign_id: UUID | str) -> dict | None:
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
) -> tuple[list[dict], int]:
    """List campaigns for a user (paginated)."""
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
) -> dict | None:
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
            assignments.append(f"{field} = :{ field}")
            params[field] = json.dumps(value)
        else:
            assignments.append(f"{field} = :{field}")
            params[field] = value
    
    params["updated_at"] = "CURRENT_TIMESTAMP"
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


def get_campaign_clips(campaign_id: UUID | str) -> list[dict]:
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
    publish_dates: dict[str, list[str]],  # {job_id: [clip_indices]}
) -> int:
    """Schedule clips from specific jobs in a campaign for publishing.
    
    Args:
        campaign_id: Campaign ID
        publish_dates: Mapping of job_id to list of clip indices to schedule
    
    Returns:
        Number of clips scheduled
    """
    from datetime import datetime, timedelta
    
    campaign = get_campaign(campaign_id)
    if not campaign:
        return 0
    
    schedule_config = campaign.get("schedule_config", {})
    interval_days = schedule_config.get("publish_interval_days", 1)
    
    scheduled_count = 0
    current_date = datetime.now()
    
    for job_id_str, clip_indices in publish_dates.items():
        for idx, clip_idx in enumerate(clip_indices):
            # Calculate publish date: base date + (index * interval_days)
            publish_date = current_date + timedelta(days=idx * interval_days)
            
            # Update job with scheduled publish date for this clip
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


# ============================================================================
# Content DNA Queries (Phase 3)
# ============================================================================

def record_content_signal(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    signal_type: str,
    metadata: dict | None = None,
) -> dict:
    """Record a user interaction signal for a clip."""
    query = text(
        """
        INSERT INTO content_signals (user_id, job_id, clip_index, signal_type, signal_metadata)
        VALUES (:user_id, :job_id, :clip_index, :signal_type, :metadata)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "job_id": str(job_id),
                "clip_index": clip_index,
                "signal_type": signal_type,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        ).one()
    return dict(row._mapping)


def get_user_score_weights(user_id: UUID | str) -> dict | None:
    """Retrieve score weights for a user."""
    query = text("SELECT * FROM user_score_weights WHERE user_id = :user_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()
    
    if not row:
        return None
    
    data = dict(row._mapping)
    if isinstance(data.get("weights"), str):
        try:
            data["weights"] = json.loads(data["weights"])
        except json.JSONDecodeError:
            pass
    if isinstance(data.get("manual_overrides"), str):
        try:
            data["manual_overrides"] = json.loads(data["manual_overrides"])
        except json.JSONDecodeError:
            data["manual_overrides"] = []
    else:
        data["manual_overrides"] = data.get("manual_overrides") or []
    return data


def update_user_score_weights(
    user_id: UUID | str,
    weights: dict,
    signal_count: int,
    confidence_score: float,
    manual_overrides: list[str] | None = None,
) -> dict:
    """Update or create score weights for a user."""
    query = text(
        """
        INSERT INTO user_score_weights (user_id, weights, signal_count, confidence_score, manual_overrides, last_updated)
        VALUES (:user_id, :weights, :signal_count, :confidence_score, :manual_overrides, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            weights = EXCLUDED.weights,
            signal_count = EXCLUDED.signal_count,
            confidence_score = EXCLUDED.confidence_score,
            manual_overrides = COALESCE(EXCLUDED.manual_overrides, user_score_weights.manual_overrides),
            last_updated = EXCLUDED.last_updated
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "weights": json.dumps(weights),
                "signal_count": signal_count,
                "confidence_score": confidence_score,
                "manual_overrides": json.dumps(manual_overrides) if manual_overrides is not None else None,
            },
        ).one()
    
    data = dict(row._mapping)
    if isinstance(data.get("weights"), str):
        data["weights"] = json.loads(data["weights"])
    if isinstance(data.get("manual_overrides"), str):
        data["manual_overrides"] = json.loads(data["manual_overrides"])
    return data


def get_user_signal_counts(user_id: UUID | str) -> dict[str, int]:
    """Get counts of each signal type for a user."""
    query = text(
        """
        SELECT signal_type, COUNT(*) as count
        FROM content_signals
        WHERE user_id = :user_id
        GROUP BY signal_type
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).all()
    
    return {row.signal_type: row.count for row in rows}


def create_api_key(
    user_id: UUID | str,
    name: str,
    key_hash: str,
    rate_limit_per_min: int = 60,
    expires_at: Any = None,
) -> dict:
    """Create a new API key for a user."""
    import secrets
    from datetime import datetime
    
    key_prefix = f"clipmind_{secrets.token_hex(6)}"
    
    query = text(
        """
        INSERT INTO api_keys
        (user_id, name, key_prefix, key_hash, rate_limit_per_min, is_active, expires_at)
        VALUES (:user_id, :name, :key_prefix, :key_hash, :rate_limit_per_min, true, :expires_at)
        RETURNING id, key_prefix, name, is_active, rate_limit_per_min, created_at, expires_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "key_prefix": key_prefix,
                "key_hash": key_hash,
                "rate_limit_per_min": rate_limit_per_min,
                "expires_at": expires_at,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_api_key_by_prefix(key_prefix: str) -> dict | None:
    """Get API key by prefix (for authentication)."""
    query = text(
        """
        SELECT id, user_id, name, key_prefix, key_hash, is_active, rate_limit_per_min, last_used_at
        FROM api_keys WHERE key_prefix = :key_prefix
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, {"key_prefix": key_prefix}).fetchone()
    
    return dict(row._mapping) if row else None


def list_user_api_keys(user_id: UUID | str, limit: int = 50, offset: int = 0) -> dict:
    """List all API keys for a user."""
    query = text(
        """
        SELECT id, name, key_prefix, is_active, rate_limit_per_min,
               last_used_at, created_at, expires_at
        FROM api_keys
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM api_keys WHERE user_id = :user_id")
    
    with engine.begin() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "keys": [dict(row._mapping) for row in rows],
        "total": total,
    }


def revoke_api_key(api_key_id: UUID | str) -> bool:
    """Revoke an API key by setting is_active to false."""
    query = text("UPDATE api_keys SET is_active = false WHERE id = :id")
    
    with engine.begin() as connection:
        result = connection.execute(query, {"id": str(api_key_id)})
    
    return result.rowcount > 0


def update_api_key_last_used(key_prefix: str) -> None:
    """Update the last_used_at timestamp for an API key."""
    from datetime import datetime, timezone
    query = text(
        "UPDATE api_keys SET last_used_at = :now WHERE key_prefix = :key_prefix"
    )
    
    with engine.begin() as connection:
        connection.execute(query, {"key_prefix": key_prefix, "now": datetime.now(timezone.utc)})


# ============================================================================
# Webhook Functions (Feature 4: ClipMind API)
# ============================================================================

def create_webhook(
    user_id: UUID | str,
    url: str,
    event_types: list[str],
    secret: str,
    timeout_seconds: int = 30,
) -> dict:
    """Create a new webhook endpoint."""
    query = text(
        """
        INSERT INTO webhooks
        (user_id, url, event_types, secret, timeout_seconds, is_active)
        VALUES (:user_id, :url, :event_types, :secret, :timeout_seconds, true)
        RETURNING id, user_id, url, event_types, secret, is_active, 
                  timeout_seconds, retry_count, retry_max, created_at, updated_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "url": url,
                "event_types": event_types,
                "secret": secret,
                "timeout_seconds": timeout_seconds,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_webhook(webhook_id: UUID | str) -> dict | None:
    """Get a webhook by ID."""
    query = text(
        """
        SELECT id, user_id, url, event_types, secret, is_active, 
               timeout_seconds, retry_count, retry_max, created_at, updated_at
        FROM webhooks WHERE id = :id
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, {"id": str(webhook_id)}).fetchone()
    
    return dict(row._mapping) if row else None


def list_user_webhooks(user_id: UUID | str, limit: int = 50, offset: int = 0) -> dict:
    """List all webhooks for a user."""
    query = text(
        """
        SELECT id, url, event_types, is_active, timeout_seconds, 
               retry_count, retry_max, created_at, updated_at
        FROM webhooks
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM webhooks WHERE user_id = :user_id")
    
    with engine.begin() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "webhooks": [dict(row._mapping) for row in rows],
        "total": total,
    }


def list_active_webhooks_for_event(event_type: str) -> list[dict]:
    """Get all active webhooks subscribed to an event type."""
    query = text(
        """
        SELECT id, user_id, url, event_types, secret, timeout_seconds
        FROM webhooks
        WHERE is_active = true AND :event_type = ANY(event_types)
        """
    )
    
    with engine.begin() as connection:
        rows = connection.execute(query, {"event_type": event_type}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_webhook(webhook_id: UUID | str, **fields: Any) -> dict | None:
    """Update webhook fields (url, event_types, is_active, timeout_seconds)."""
    allowed_fields = {"url", "event_types", "is_active", "timeout_seconds"}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
    
    if not update_fields:
        return get_webhook(webhook_id)
    
    set_clause = ", ".join(f"{k} = :{k}" for k in update_fields.keys())
    query = text(
        f"""
        UPDATE webhooks SET {set_clause}, updated_at = NOW()
        WHERE id = :id
        RETURNING id, url, event_types, is_active, timeout_seconds, 
                  retry_count, retry_max, created_at, updated_at
        """
    )
    
    params = {"id": str(webhook_id), **update_fields}
    
    with engine.begin() as connection:
        row = connection.execute(query, params).fetchone()
    
    return dict(row._mapping) if row else None


def delete_webhook(webhook_id: UUID | str) -> bool:
    """Delete a webhook and all associated delivery logs."""
    query_delete = text("DELETE FROM webhooks WHERE id = :id")
    
    with engine.begin() as connection:
        result = connection.execute(query_delete, {"id": str(webhook_id)})
    
    return result.rowcount > 0


def create_webhook_delivery(
    webhook_id: UUID | str,
    event_type: str,
    event_data: dict,
) -> dict:
    """Create a new webhook delivery record."""
    query = text(
        """
        INSERT INTO webhook_deliveries
        (webhook_id, event_type, event_data, status)
        VALUES (:webhook_id, :event_type, :event_data, 'pending')
        RETURNING id, webhook_id, event_type, status, attempt_count, created_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "webhook_id": str(webhook_id),
                "event_type": event_type,
                "event_data": json.dumps(event_data),
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def list_webhook_deliveries(
    webhook_id: UUID | str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List delivery logs for a webhook."""
    query = text(
        """
        SELECT id, webhook_id, event_type, http_status, status, 
               attempt_count, error_message, created_at, delivered_at, next_retry_at
        FROM webhook_deliveries
        WHERE webhook_id = :webhook_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM webhook_deliveries WHERE webhook_id = :webhook_id")
    failed_count_query = text(
        "SELECT COUNT(*) FROM webhook_deliveries WHERE webhook_id = :webhook_id AND status = 'failed'"
    )
    pending_count_query = text(
        "SELECT COUNT(*) FROM webhook_deliveries WHERE webhook_id = :webhook_id AND status = 'pending'"
    )
    
    with engine.begin() as connection:
        rows = connection.execute(
            query,
            {"webhook_id": str(webhook_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"webhook_id": str(webhook_id)}).scalar()
        failed_count = connection.execute(
            failed_count_query, {"webhook_id": str(webhook_id)}
        ).scalar()
        pending_count = connection.execute(
            pending_count_query, {"webhook_id": str(webhook_id)}
        ).scalar()
    
    return {
        "webhook_id": str(webhook_id),
        "deliveries": [dict(row._mapping) for row in rows],
        "total": total,
        "failed_count": failed_count,
        "pending_count": pending_count,
    }


def get_pending_webhook_deliveries() -> list[dict]:
    """Get all pending webhook deliveries ready to retry."""
    query = text(
        """
        SELECT id, webhook_id, event_type, event_data, attempt_count, retry_max
        FROM webhook_deliveries
        WHERE status = 'pending' 
          AND (next_retry_at IS NULL OR next_retry_at <= NOW())
          AND attempt_count < retry_max
        ORDER BY created_at ASC
        LIMIT 100
        """
    )
    
    with engine.begin() as connection:
        rows = connection.execute(query).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_webhook_delivery(
    delivery_id: UUID | str,
    http_status: int | None = None,
    response_body: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    next_retry_at: Any = None,
) -> dict | None:
    """Update webhook delivery status after an attempt."""
    query = text(
        """
        UPDATE webhook_deliveries
        SET http_status = COALESCE(:http_status, http_status),
            response_body = COALESCE(:response_body, response_body),
            status = COALESCE(:status, status),
            error_message = COALESCE(:error_message, error_message),
            next_retry_at = COALESCE(:next_retry_at, next_retry_at),
            attempt_count = attempt_count + 1,
            delivered_at = CASE WHEN :status = 'delivered' THEN NOW() ELSE delivered_at END
        WHERE id = :id
        RETURNING id, webhook_id, status, attempt_count, http_status, delivered_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "id": str(delivery_id),
                "http_status": http_status,
                "response_body": response_body,
                "status": status,
                "error_message": error_message,
                "next_retry_at": next_retry_at,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_webhook_delivery(delivery_id: UUID | str) -> dict | None:
    """Get a webhook delivery record by ID."""
    query = text(
        """
        SELECT id, webhook_id, event_type, event_data, http_status, response_body, 
               status, attempt_count, retry_max, error_message, created_at, 
               delivered_at, next_retry_at
        FROM webhook_deliveries WHERE id = :id
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, {"id": str(delivery_id)}).fetchone()
    
    return dict(row._mapping) if row else None


# ============================================================================
# Integration Functions (Feature 4: Integrations with Zapier/Make)
# ============================================================================

def create_integration(
    user_id: UUID | str,
    integration_type: str,
    name: str,
    trigger_events: list[str],
    config: dict | None = None,
) -> dict:
    """Create a new integration."""
    if config is None:
        config = {}
    
    query = text(
        """
        INSERT INTO integrations
        (user_id, integration_type, name, trigger_events, config, is_active)
        VALUES (:user_id, :integration_type, :name, :trigger_events, :config, true)
        RETURNING id, user_id, integration_type, name, trigger_events, config, 
                  is_active, last_triggered_at, created_at, updated_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "integration_type": integration_type,
                "name": name,
                "trigger_events": trigger_events,
                "config": json.dumps(config),
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_integration(integration_id: UUID | str) -> dict | None:
    """Get an integration by ID."""
    query = text(
        """
        SELECT id, user_id, integration_type, name, trigger_events, config,
               is_active, last_triggered_at, created_at, updated_at
        FROM integrations WHERE id = :id
        """
    )
    
    with engine.connect() as connection:
        row = connection.execute(query, {"id": str(integration_id)}).one_or_none()
    
    return dict(row._mapping) if row else None


def list_user_integrations(
    user_id: UUID | str,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List all integrations for a user."""
    query = text(
        """
        SELECT id, integration_type, name, trigger_events, is_active,
               last_triggered_at, created_at, updated_at
        FROM integrations
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM integrations WHERE user_id = :user_id")
    
    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "integrations": [dict(row._mapping) for row in rows],
        "total": total,
    }


def list_active_integrations_for_event(event_type: str) -> list[dict]:
    """Get all active integrations subscribed to an event type."""
    query = text(
        """
        SELECT id, user_id, integration_type, name, trigger_events, config
        FROM integrations
        WHERE is_active = true AND :event_type = ANY(trigger_events)
        """
    )
    
    with engine.connect() as connection:
        rows = connection.execute(query, {"event_type": event_type}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_integration(integration_id: UUID | str, **fields: Any) -> dict | None:
    """Update integration fields."""
    allowed_fields = {"name", "trigger_events", "is_active", "config"}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
    
    if not update_fields:
        return get_integration(integration_id)
    
    assignments = []
    params = {"id": str(integration_id)}
    
    for field, value in update_fields.items():
        if field == "config" and isinstance(value, dict):
            assignments.append(f"{field} = :{ field}")
            params[field] = json.dumps(value)
        else:
            assignments.append(f"{field} = :{field}")
            params[field] = value
    
    assignments.append("updated_at = NOW()")
    
    query = text(
        f"""
        UPDATE integrations SET {", ".join(assignments)}
        WHERE id = :id
        RETURNING id, integration_type, name, trigger_events, config,
                  is_active, last_triggered_at, created_at, updated_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, params).fetchone()
    
    return dict(row._mapping) if row else None


def delete_integration(integration_id: UUID | str) -> bool:
    """Delete an integration."""
    query = text("DELETE FROM integrations WHERE id = :id")
    
    with engine.begin() as connection:
        result = connection.execute(query, {"id": str(integration_id)})
    
    return result.rowcount > 0


def update_integration_last_triggered(integration_id: UUID | str) -> None:
    """Update the last_triggered_at timestamp for an integration."""
    query = text(
        "UPDATE integrations SET last_triggered_at = NOW() WHERE id = :id"
    )
    
    with engine.begin() as connection:
        connection.execute(query, {"id": str(integration_id)})


# ============================================================================
# PERFORMANCE QUERIES (Clip Intelligence)
# ============================================================================

def create_or_update_performance(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
    views: int,
    likes: int,
    saves: int,
    shares: int,
    comments: int,
    average_watch_time_seconds: float | None = None,
    completion_rate: float | None = None,
    platform_clip_id: str | None = None,
    published_date: datetime | None = None,
) -> dict:
    """Create or update performance metrics for a clip on a platform.
    
    If a record exists for this job_id + clip_index + platform, update it.
    Otherwise, create a new record.
    """
    # Calculate derived metrics
    engagement_score = 0.0
    save_rate = 0.0
    share_rate = 0.0
    comment_rate = 0.0
    
    if views > 0:
        engagement_score = (likes + saves + shares + comments) / views
        save_rate = saves / views
        share_rate = shares / views
        comment_rate = comments / views
    
    query = text("""
        INSERT INTO clip_performance (
            user_id, job_id, clip_index, platform, platform_clip_id,
            views, likes, saves, shares, comments,
            engagement_score, save_rate, share_rate, comment_rate,
            average_watch_time_seconds, completion_rate, published_date,
            synced_at
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :platform_clip_id,
            :views, :likes, :saves, :shares, :comments,
            :engagement_score, :save_rate, :share_rate, :comment_rate,
            :average_watch_time_seconds, :completion_rate, :published_date,
            NOW()
        )
        ON CONFLICT (user_id, job_id, clip_index, platform)
        DO UPDATE SET
            views = :views,
            likes = :likes,
            saves = :saves,
            shares = :shares,
            comments = :comments,
            engagement_score = :engagement_score,
            save_rate = :save_rate,
            share_rate = :share_rate,
            comment_rate = :comment_rate,
            average_watch_time_seconds = :average_watch_time_seconds,
            completion_rate = :completion_rate,
            synced_at = NOW(),
            updated_at = NOW()
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "platform": platform,
            "platform_clip_id": platform_clip_id,
            "views": views,
            "likes": likes,
            "saves": saves,
            "shares": shares,
            "comments": comments,
            "engagement_score": engagement_score,
            "save_rate": save_rate,
            "share_rate": share_rate,
            "comment_rate": comment_rate,
            "average_watch_time_seconds": average_watch_time_seconds,
            "completion_rate": completion_rate,
            "published_date": published_date,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_clip_performance(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
) -> dict | None:
    """Get performance metrics for a specific clip on a platform."""
    query = text("""
        SELECT * FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id 
              AND clip_index = :clip_index AND platform = :platform
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "platform": platform,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_performance_for_job(
    user_id: UUID | str,
    job_id: UUID | str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List all performance records for a job across all platforms.
    
    Returns:
        Tuple of (list of performance records, total count)
    """
    query = text("""
        SELECT * FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id
        ORDER BY clip_index, platform
        LIMIT :limit OFFSET :offset
    """)
    
    count_query = text("""
        SELECT COUNT(*) as count FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id
    """)
    
    params = {
        "user_id": str(user_id),
        "job_id": str(job_id),
        "limit": limit,
        "offset": offset,
    }
    
    with engine.begin() as connection:
        rows = connection.execute(query, params).fetchall()
        total = connection.execute(count_query, params).scalar()
    
    return ([dict(row._mapping) for row in rows], total)


def list_performance_by_platform(
    user_id: UUID | str,
    platform: str,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List all performance records for a user on a specific platform.
    
    Returns:
        Tuple of (list of performance records, total count)
    """
    query = text("""
        SELECT * FROM clip_performance
        WHERE user_id = :user_id AND platform = :platform
        ORDER BY synced_at DESC
        LIMIT :limit OFFSET :offset
    """)
    
    count_query = text("""
        SELECT COUNT(*) as count FROM clip_performance
        WHERE user_id = :user_id AND platform = :platform
    """)
    
    params = {
        "user_id": str(user_id),
        "platform": platform,
        "limit": limit,
        "offset": offset,
    }
    
    with engine.begin() as connection:
        rows = connection.execute(query, params).fetchall()
        total = connection.execute(count_query, params).scalar()
    
    return ([dict(row._mapping) for row in rows], total)


def get_job_performance_summary(
    user_id: UUID | str,
    job_id: UUID | str,
) -> dict | None:
    """Get aggregated performance summary for all clips in a job.
    
    Returns summary stats across all clips and platforms.
    """
    query = text("""
        SELECT
            COUNT(DISTINCT clip_index) as total_clips,
            COUNT(DISTINCT platform) as platform_count,
            STRING_AGG(DISTINCT platform, ',') as platforms,
            SUM(views)::INTEGER as total_views,
            SUM(likes)::INTEGER as total_likes,
            SUM(saves)::INTEGER as total_saves,
            SUM(shares)::INTEGER as total_shares,
            SUM(comments)::INTEGER as total_comments,
            AVG(engagement_score)::FLOAT as overall_engagement_score,
            AVG(completion_rate)::FLOAT as average_completion_rate,
            MAX(synced_at)::TIMESTAMP as latest_synced_at
        FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_best_and_worst_clips(
    user_id: UUID | str,
    job_id: UUID | str,
) -> dict:
    """Get best and worst performing clips in a job by engagement score.
    
    Returns:
        Dict with 'best_clip_index', 'worst_clip_index', or None if no data
    """
    query = text("""
        WITH clip_avg_engagement AS (
            SELECT
                clip_index,
                AVG(engagement_score) as avg_engagement
            FROM clip_performance
            WHERE user_id = :user_id AND job_id = :job_id
            GROUP BY clip_index
        )
        SELECT
            (SELECT clip_index FROM clip_avg_engagement ORDER BY avg_engagement DESC LIMIT 1) as best_clip_index,
            (SELECT clip_index FROM clip_avg_engagement ORDER BY avg_engagement ASC LIMIT 1) as worst_clip_index
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
        }).fetchone()
    
    if row:
        result = dict(row._mapping)
        # Filter out None values
        return {k: v for k, v in result.items() if v is not None}
    
    return {}


def get_top_platform(
    user_id: UUID | str,
    job_id: UUID | str,
) -> str | None:
    """Get the platform with most total engagement for a job."""
    query = text("""
        SELECT
            platform,
            SUM(engagement_score) as total_engagement
        FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id
        GROUP BY platform
        ORDER BY total_engagement DESC
        LIMIT 1
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
        }).fetchone()
    
    return row.platform if row else None


def get_platform_performance(
    user_id: UUID | str,
    job_id: UUID | str,
    platform: str,
) -> dict | None:
    """Get aggregated performance for all clips on a specific platform."""
    query = text("""
        SELECT
            :platform as platform,
            COUNT(DISTINCT clip_index) as total_clips,
            SUM(views)::INTEGER as total_views,
            SUM(likes)::INTEGER as total_likes,
            SUM(saves)::INTEGER as total_saves,
            SUM(shares)::INTEGER as total_shares,
            SUM(comments)::INTEGER as total_comments,
            AVG(engagement_score)::FLOAT as average_engagement_score,
            AVG(completion_rate)::FLOAT as average_completion_rate
        FROM clip_performance
        WHERE user_id = :user_id AND job_id = :job_id AND platform = :platform
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "platform": platform,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def create_performance_alert(
    user_id: UUID | str,
    clip_perf_id: UUID | str,
    alert_type: str,  # milestone, anomaly, trending
    message: str,
    metric_name: str | None = None,
    metric_value: float | None = None,
    threshold: float | None = None,
) -> dict:
    """Create a performance alert for a clip."""
    query = text("""
        INSERT INTO performance_alerts (
            user_id, clip_perf_id, alert_type, message,
            metric_name, metric_value, threshold
        ) VALUES (
            :user_id, :clip_perf_id, :alert_type, :message,
            :metric_name, :metric_value, :threshold
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "clip_perf_id": str(clip_perf_id),
            "alert_type": alert_type,
            "message": message,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold": threshold,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_performance_alerts(
    user_id: UUID | str,
    limit: int = 50,
    offset: int = 0,
    unread_only: bool = False,
) -> tuple[list[dict], int]:
    """List performance alerts for a user.
    
    Returns:
        Tuple of (list of alerts, total count)
    """
    where_clause = "WHERE user_id = :user_id"
    if unread_only:
        where_clause += " AND is_read = FALSE"
    
    query = text(f"""
        SELECT * FROM performance_alerts
        {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    
    count_query = text(f"""
        SELECT COUNT(*) as count FROM performance_alerts
        {where_clause}
    """)
    
    params = {
        "user_id": str(user_id),
        "limit": limit,
        "offset": offset,
    }
    
    with engine.begin() as connection:
        rows = connection.execute(query, params).fetchall()
        total = connection.execute(count_query, params).scalar()
    
    return ([dict(row._mapping) for row in rows], total)


    return result.rowcount > 0


def upsert_clip_performance(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
    source_type: str = "real",
    ai_predicted_score: float | None = None,
    views: int | None = None,
    likes: int | None = None,
    saves: int | None = None,
    shares: int | None = None,
    comments: int | None = None,
    engagement_score: float | None = None,
    performance_delta: float | None = None,
    milestone_tier: str | None = None,
    window_complete: bool | None = None,
    synced_at: datetime | None = None,
) -> dict:
    """Insert or update a clip performance record."""
    query = text("""
        INSERT INTO clip_performance (
            user_id, job_id, clip_index, platform, source_type,
            ai_predicted_score, performance_delta, milestone_tier, window_complete,
            views, likes, saves, shares, comments, engagement_score, synced_at
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :source_type,
            :ai_predicted_score, COALESCE(:performance_delta, 0.0), :milestone_tier, COALESCE(:window_complete, FALSE),
            COALESCE(:views, 0), COALESCE(:likes, 0), COALESCE(:saves, 0), COALESCE(:shares, 0), 
            COALESCE(:comments, 0), COALESCE(:engagement_score, 0.0), COALESCE(:synced_at, NOW())
        )
        ON CONFLICT (user_id, job_id, clip_index, platform) DO UPDATE SET
            source_type = EXCLUDED.source_type,
            views = COALESCE(EXCLUDED.views, clip_performance.views),
            likes = COALESCE(EXCLUDED.likes, clip_performance.likes),
            saves = COALESCE(EXCLUDED.saves, clip_performance.saves),
            shares = COALESCE(EXCLUDED.shares, clip_performance.shares),
            comments = COALESCE(EXCLUDED.comments, clip_performance.comments),
            engagement_score = COALESCE(EXCLUDED.engagement_score, clip_performance.engagement_score),
            performance_delta = COALESCE(EXCLUDED.performance_delta, clip_performance.performance_delta),
            milestone_tier = COALESCE(EXCLUDED.milestone_tier, clip_performance.milestone_tier),
            window_complete = COALESCE(EXCLUDED.window_complete, clip_performance.window_complete),
            synced_at = EXCLUDED.synced_at,
            updated_at = NOW()
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "platform": platform,
            "source_type": source_type,
            "ai_predicted_score": ai_predicted_score,
            "performance_delta": performance_delta,
            "milestone_tier": milestone_tier,
            "window_complete": window_complete,
            "views": views,
            "likes": likes,
            "saves": saves,
            "shares": shares,
            "comments": comments,
            "engagement_score": engagement_score,
            "synced_at": synced_at,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_user_performance_summary(user_id: UUID | str) -> dict:
    """Get aggregated metrics for the dashboard."""
    query = text("""
        SELECT
            COUNT(DISTINCT (job_id, clip_index)) as total_clips,
            COALESCE(SUM(views), 0)::INTEGER as total_views,
            COALESCE(SUM(likes), 0)::INTEGER as total_likes,
            COALESCE(SUM(saves), 0)::INTEGER as total_saves,
            COALESCE(AVG(engagement_score), 0.0)::FLOAT as avg_engagement,
            (SELECT source_type FROM clip_performance WHERE user_id = :user_id LIMIT 1) as data_source
        FROM clip_performance
        WHERE user_id = :user_id
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).fetchone()
    
    data = dict(row._mapping) if row else {}
    if not data.get("data_source"):
        data["data_source"] = "real" # Fallback
    return data


def save_platform_credentials(
    user_id: UUID | str,
    platform: str,
    access_token_encrypted: str,
    account_id: str,
    account_name: str,
    scopes: list[str],
    refresh_token_encrypted: str | None = None,
    expires_at: datetime | None = None,
) -> dict:
    """Save or update platform credentials for API syncing."""
    query = text("""
        INSERT INTO platform_credentials (
            user_id, platform, access_token_encrypted, refresh_token_encrypted,
            expires_at, account_id, account_name, scopes
        ) VALUES (
            :user_id, :platform, :access_token_encrypted, :refresh_token_encrypted,
            :expires_at, :account_id, :account_name, :scopes
        )
        ON CONFLICT (user_id, platform)
        DO UPDATE SET
            access_token_encrypted = :access_token_encrypted,
            refresh_token_encrypted = :refresh_token_encrypted,
            expires_at = :expires_at,
            account_id = :account_id,
            account_name = :account_name,
            scopes = :scopes,
            updated_at = NOW()
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
            "access_token_encrypted": access_token_encrypted,
            "refresh_token_encrypted": refresh_token_encrypted,
            "expires_at": expires_at,
            "account_id": account_id,
            "account_name": account_name,
            "scopes": ','.join(scopes),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_platform_credentials(
    user_id: UUID | str,
    platform: str,
) -> dict | None:
    """Get platform credentials for a user."""
    query = text("""
        SELECT * FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_platform_accounts(
    user_id: UUID | str,
) -> list[dict]:
    """List all connected platform accounts for a user."""
    query = text("""
        SELECT id, platform, account_id, account_name, scopes, synced_at, created_at
        FROM platform_credentials
        WHERE user_id = :user_id
        ORDER BY platform
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def delete_platform_credentials(
    user_id: UUID | str,
    platform: str,
) -> bool:
    """Delete platform credentials for a user."""
    query = text("""
        DELETE FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
    """)
    
    with engine.begin() as connection:
        result = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
        })
    
    return result.rowcount > 0


# ============================================================================
# CONTENT DNA QUERIES (Personalized AI Learning)
# ============================================================================

def log_content_signal(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    signal_type: str,
    signal_metadata: dict | None = None,
) -> dict:
    """Log a user engagement signal for Content DNA learning."""
    query = text("""
        INSERT INTO content_signals (
            user_id, job_id, clip_index, signal_type, signal_metadata
        ) VALUES (
            :user_id, :job_id, :clip_index, :signal_type, :signal_metadata
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "signal_type": signal_type,
            "signal_metadata": json.dumps(signal_metadata or {}),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_user_signals(
    user_id: UUID | str,
    limit: int = 100,
) -> list[dict]:
    """Get recent signals for a user."""
    query = text("""
        SELECT * FROM content_signals
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {
            "user_id": str(user_id),
            "limit": limit,
        }).fetchall()
    
    return [dict(row._mapping) for row in rows]


# Removed duplicate DNA functions (merged at line 1859)


# ============================================================================
# CLIP SEQUENCES QUERIES (Multi-clip Narratives)
# ============================================================================

def create_clip_sequence(
    user_id: UUID | str,
    job_id: UUID | str,
    sequence_title: str,
    clip_indices: list[int],
    suggested_captions: list[str],
    cliffhanger_scores: list[float],
    series_description: str | None = None,
    platform_optimizations: dict | None = None,
) -> dict:
    """Create a clip sequence."""
    query = text("""
        INSERT INTO clip_sequences (
            user_id, job_id, sequence_title, clip_indices,
            suggested_captions, cliffhanger_scores, series_description,
            platform_optimizations
        ) VALUES (
            :user_id, :job_id, :sequence_title, :clip_indices,
            :suggested_captions, :cliffhanger_scores, :series_description,
            :platform_optimizations
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "sequence_title": sequence_title,
            "clip_indices": clip_indices,
            "suggested_captions": suggested_captions,
            "cliffhanger_scores": cliffhanger_scores,
            "series_description": series_description,
            "platform_optimizations": json.dumps(platform_optimizations or {}),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_sequences_for_job(
    user_id: UUID | str,
    job_id: UUID | str,
) -> list[dict]:
    """List all sequences detected for a job."""
    query = text("""
        SELECT * FROM clip_sequences
        WHERE user_id = :user_id AND job_id = :job_id
        ORDER BY created_at DESC
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
        }).fetchall()
    
    return [dict(row._mapping) for row in rows]


# ============================================================================
# SOCIAL PUBLISHING QUERIES (One-Click Publish)
# ============================================================================

def create_social_account(
    user_id: UUID | str,
    platform: str,
    account_id: str,
    account_username: str,
    access_token_encrypted: str,
    refresh_token_encrypted: str | None = None,
    token_expires_at: datetime | None = None,
) -> dict:
    """Create connection to social media account."""
    query = text("""
        INSERT INTO social_accounts (
            user_id, platform, account_id, account_username,
            access_token_encrypted, refresh_token_encrypted, token_expires_at
        ) VALUES (
            :user_id, :platform, :account_id, :account_username,
            :access_token_encrypted, :refresh_token_encrypted, :token_expires_at
        )
        ON CONFLICT (user_id, platform, account_id)
        DO UPDATE SET
            access_token_encrypted = :access_token_encrypted,
            refresh_token_encrypted = :refresh_token_encrypted,
            token_expires_at = :token_expires_at,
            is_connected = TRUE,
            updated_at = NOW()
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
            "account_id": account_id,
            "account_username": account_username,
            "access_token_encrypted": access_token_encrypted,
            "refresh_token_encrypted": refresh_token_encrypted,
            "token_expires_at": token_expires_at,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_social_accounts(user_id: UUID | str) -> list[dict]:
    """List all connected social accounts."""
    query = text("""
        SELECT id, user_id, platform, account_id, account_username,
               is_connected, last_sync, created_at
        FROM social_accounts
        WHERE user_id = :user_id AND is_connected = TRUE
        ORDER BY platform
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def create_published_clip(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
    social_account_id: UUID | str,
    caption: str,
    hashtags: list[str] | None = None,
    platform_clip_id: str | None = None,
    published_at: datetime | None = None,
    scheduled_at: datetime | None = None,
) -> dict:
    """Create record of published clip."""
    query = text("""
        INSERT INTO published_clips (
            user_id, job_id, clip_index, platform, social_account_id,
            caption, hashtags, platform_clip_id, published_at, scheduled_at,
            status
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :social_account_id,
            :caption, :hashtags, :platform_clip_id, :published_at, :scheduled_at,
            CASE WHEN :published_at IS NOT NULL THEN 'published' 
                 WHEN :scheduled_at IS NOT NULL THEN 'scheduled'
                 ELSE 'draft' END
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "platform": platform,
            "social_account_id": str(social_account_id),
            "caption": caption,
            "hashtags": hashtags,
            "platform_clip_id": platform_clip_id,
            "published_at": published_at,
            "scheduled_at": scheduled_at,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_published_clips(
    user_id: UUID | str,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """List published clips for user."""
    query = text("""
        SELECT * FROM published_clips
        WHERE user_id = :user_id
        ORDER BY published_at DESC NULLS LAST, scheduled_at DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """)
    
    count_query = text("""
        SELECT COUNT(*) as count FROM published_clips WHERE user_id = :user_id
    """)
    
    params = {
        "user_id": str(user_id),
        "limit": limit,
        "offset": offset,
    }
    
    with engine.begin() as connection:
        rows = connection.execute(query, params).fetchall()
        total = connection.execute(count_query, params).scalar()
    
    return ([dict(row._mapping) for row in rows], total)


# ============================================================================
# WORKSPACE/TEAM QUERIES (Workspaces & Client Portals)
# ============================================================================

def create_workspace(
    owner_id: UUID | str,
    name: str,
    slug: str,
    plan: str = "starter",
) -> dict:
    """Create a new workspace."""
    query = text("""
        INSERT INTO workspaces (owner_id, name, slug, plan)
        VALUES (:owner_id, :name, :slug, :plan)
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "owner_id": str(owner_id),
            "name": name,
            "slug": slug,
            "plan": plan,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def list_user_workspaces(user_id: UUID | str) -> list[dict]:
    """List all workspaces user is member of."""
    query = text("""
        SELECT DISTINCT w.* FROM workspaces w
        JOIN workspace_members wm ON w.id = wm.workspace_id
        WHERE wm.user_id = :user_id AND w.is_active = TRUE
        ORDER BY w.created_at DESC
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def get_user_preferences(user_id: UUID | str) -> dict | None:
    """Fetch saved onboarding and preference data for a user."""
    query = text("""
        SELECT * FROM user_preferences WHERE user_id = :user_id
    """)

    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()

    if not row:
        return None

    data = dict(row._mapping)
    if isinstance(data.get("goals"), str):
        try:
            data["goals"] = json.loads(data["goals"])
        except json.JSONDecodeError:
            data["goals"] = []
    if isinstance(data.get("preferences_json"), str):
        try:
            data["preferences_json"] = json.loads(data["preferences_json"])
        except json.JSONDecodeError:
            data["preferences_json"] = {}
    return data


def save_user_preferences(
    user_id: UUID | str,
    *,
    goals: list[str] | None = None,
    target_platform: str | None = None,
    preferences: dict | None = None,
    onboarding_completed: bool = True,
) -> dict:
    """Upsert the user's onboarding choices and derived preference profile."""
    query = text("""
        INSERT INTO user_preferences (
            user_id, goals, target_platform, preferences_json, onboarding_completed
        ) VALUES (
            :user_id, :goals, :target_platform, :preferences_json, :onboarding_completed
        )
        ON CONFLICT (user_id) DO UPDATE SET
            goals = :goals,
            target_platform = :target_platform,
            preferences_json = :preferences_json,
            onboarding_completed = :onboarding_completed,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """)

    payload = {
        "user_id": str(user_id),
        "goals": json.dumps(goals or []),
        "target_platform": target_platform,
        "preferences_json": json.dumps(preferences or {}),
        "onboarding_completed": onboarding_completed,
    }

    with engine.begin() as connection:
        row = connection.execute(query, payload).one()

    data = dict(row._mapping)
    if isinstance(data.get("goals"), str):
        try:
            data["goals"] = json.loads(data["goals"])
        except json.JSONDecodeError:
            data["goals"] = []
    if isinstance(data.get("preferences_json"), str):
        try:
            data["preferences_json"] = json.loads(data["preferences_json"])
        except json.JSONDecodeError:
            data["preferences_json"] = {}
    return data


def add_workspace_member(
    workspace_id: UUID | str,
    user_id: UUID | str,
    role: str = "editor",
) -> dict:
    """Add member to workspace."""
    query = text("""
        INSERT INTO workspace_members (workspace_id, user_id, role)
        VALUES (:workspace_id, :user_id, :role)
        ON CONFLICT (workspace_id, user_id)
        DO UPDATE SET role = :role
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "role": role,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def create_workspace_client(
    workspace_id: UUID | str,
    client_name: str,
    client_contact_email: str | None = None,
    description: str | None = None,
) -> dict:
    """Create client in workspace."""
    query = text("""
        INSERT INTO workspace_clients (workspace_id, client_name, client_contact_email, description)
        VALUES (:workspace_id, :client_name, :client_contact_email, :description)
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "workspace_id": str(workspace_id),
            "client_name": client_name,
            "client_contact_email": client_contact_email,
            "description": description,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def create_client_portal(
    workspace_id: UUID | str,
    client_id: UUID | str,
    portal_slug: str,
    branding: dict | None = None,
) -> dict:
    """Create white-labeled portal for client."""
    query = text("""
        INSERT INTO client_portals (workspace_id, client_id, portal_slug, branding)
        VALUES (:workspace_id, :client_id, :portal_slug, :branding)
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "workspace_id": str(workspace_id),
            "client_id": str(client_id),
            "portal_slug": portal_slug,
            "branding": json.dumps(branding or {}),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_client_portal(portal_slug: str) -> dict | None:
    """Get client portal by slug."""
    query = text("""
        SELECT * FROM client_portals WHERE portal_slug = :portal_slug
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {"portal_slug": portal_slug}).fetchone()
    
    return dict(row._mapping) if row else None


def log_workspace_audit(
    workspace_id: UUID | str,
    action: str,
    user_id: UUID | str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | str | None = None,
    details: dict | None = None,
) -> dict:
    """Log action in workspace audit trail."""
    query = text("""
        INSERT INTO workspace_audit_logs (
            workspace_id, action, user_id, resource_type, resource_id, details
        ) VALUES (
            :workspace_id, :action, :user_id, :resource_type, :resource_id, :details
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "workspace_id": str(workspace_id),
            "action": action,
            "user_id": str(user_id) if user_id else None,
            "resource_type": resource_type,
            "resource_id": str(resource_id) if resource_id else None,
            "details": json.dumps(details or {}),
        }).fetchone()
    
    return dict(row._mapping) if row else None


# ============================================================================
# RENDER JOB QUERIES (Preview Studio - In-browser Caption Editing)
# ============================================================================

def create_render_job(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    edited_srt: str,
    caption_style: dict | None = None,
) -> dict | None:
    """Create a render job for edited captions."""
    query = text("""
        INSERT INTO render_jobs (
            user_id, job_id, clip_index, edited_srt, caption_style, status
        ) VALUES (
            :user_id, :job_id, :clip_index, :edited_srt, :caption_style, 'queued'
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "edited_srt": edited_srt,
            "caption_style": json.dumps(caption_style or {}),
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_render_job(render_job_id: UUID | str) -> dict | None:
    """Get render job details."""
    query = text("""
        SELECT * FROM render_jobs WHERE id = :render_job_id
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {"render_job_id": str(render_job_id)}).fetchone()
    
    return dict(row._mapping) if row else None


def list_render_jobs(
    job_id: UUID | str,
    limit: int = 50,
) -> list[dict]:
    """List render jobs for a job."""
    query = text("""
        SELECT * FROM render_jobs
        WHERE job_id = :job_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    
    with engine.begin() as connection:
        rows = connection.execute(query, {
            "job_id": str(job_id),
            "limit": limit,
        }).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_render_job_status(
    render_job_id: UUID | str,
    status: str,
    progress_percent: int | None = None,
    output_url: str | None = None,
    error_message: str | None = None,
) -> dict | None:
    """Update render job status."""
    query = text("""
        UPDATE render_jobs SET
            status = :status,
            progress_percent = COALESCE(:progress_percent, progress_percent),
            output_url = COALESCE(:output_url, output_url),
            error_message = COALESCE(:error_message, error_message),
            completed_at = CASE WHEN :status = 'completed' OR :status = 'failed'
                          THEN NOW() ELSE completed_at END
        WHERE id = :render_job_id
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "render_job_id": str(render_job_id),
            "status": status,
            "progress_percent": progress_percent,
            "output_url": output_url,
            "error_message": error_message,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def update_published_clip_status(
    published_clip_id: UUID | str,
    status: str,
    platform_clip_id: str | None = None,
    platform_url: str | None = None,
    engagement_metrics: dict | None = None,
) -> dict | None:
    """Update published clip status and metrics."""
    query = text("""
        UPDATE published_clips SET
            status = :status,
            platform_clip_id = COALESCE(:platform_clip_id, platform_clip_id),
            platform_url = COALESCE(:platform_url, platform_url),
            engagement_metrics = COALESCE(:engagement_metrics, engagement_metrics),
            updated_at = NOW()
        WHERE id = :published_clip_id
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "published_clip_id": str(published_clip_id),
            "status": status,
            "platform_clip_id": platform_clip_id,
            "platform_url": platform_url,
            "engagement_metrics": json.dumps(engagement_metrics) if engagement_metrics else None,
        }).fetchone()
    return dict(row._mapping) if row else None


def get_social_account(social_account_id: UUID | str) -> dict | None:
    """Retrieve social account tokens. Returns mock on DB failure."""
    query = text("SELECT * FROM platform_accounts WHERE id = :id")
    with engine.begin() as connection:
        try:
            row = connection.execute(query, {"id": str(social_account_id)}).fetchone()
            return dict(row._mapping) if row else None
        except Exception:
            return {
                "id": str(social_account_id),
                "access_token": "mock_token",
                "refresh_token": "mock_refresh",
                "client_id": "mock_client",
                "client_secret": "mock_secret"
            }


def create_published_clip(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    platform: str,
    social_account_id: UUID | str,
    caption: str,
    hashtags: list[str] | None,
    platform_clip_id: str,
    published_at: datetime,
    scheduled_at: datetime | None,
) -> dict | None:
    """Insert into published_clips table."""
    query = text("""
        INSERT INTO published_clips (
            user_id, job_id, clip_index, platform, social_account_id,
            caption, hashtags, platform_clip_id, published_at, scheduled_at, status
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :social_account_id,
            :caption, :hashtags, :platform_clip_id, :published_at, :scheduled_at, 'published'
        ) RETURNING *
    """)
    with engine.begin() as connection:
        try:
            row = connection.execute(query, {
                "user_id": str(user_id),
                "job_id": str(job_id),
                "clip_index": clip_index,
                "platform": platform,
                "social_account_id": str(social_account_id),
                "caption": caption,
                "hashtags": json.dumps(hashtags) if hashtags else None,
                "platform_clip_id": platform_clip_id,
                "published_at": published_at,
                "scheduled_at": scheduled_at,
            }).fetchone()
            return dict(row._mapping) if row else None
        except Exception:
            return {"status": "simulated", "platform_clip_id": platform_clip_id}

# ============================================================================
# Autopilot Queries (Phase 4)
# ============================================================================

def create_connected_source(
    user_id: str,
    name: str,
    source_type: str,
    config: dict,
) -> dict:
    """Create a new automated source for video ingestion."""
    query = text(
        """
        INSERT INTO connected_sources (user_id, name, source_type, config_json)
        VALUES (:user_id, :name, :source_type, :config)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "source_type": source_type,
                "config": json.dumps(config),
            },
        ).one()
    
    data = dict(row._mapping)
    if isinstance(data.get("config_json"), str):
        data["config_json"] = json.loads(data["config_json"])
    return data


def list_active_sources_for_polling() -> list[dict]:
    """Get all enabled sources with their config."""
    query = text("SELECT * FROM connected_sources WHERE is_active = true")
    with engine.connect() as connection:
        rows = connection.execute(query).all()
    
    results = []
    for row in rows:
        data = dict(row._mapping)
        if isinstance(data.get("config_json"), str):
            data["config_json"] = json.loads(data["config_json"])
        results.append(data)
    return results


def update_source_status(
    source_id: str, 
    last_error: str | None = None,
    success: bool = False
) -> None:
    """Track polling health (error/success)."""
    now = datetime.now()
    if success:
        query = text("""
            UPDATE connected_sources 
            SET last_polled_at = :now, 
                last_success_at = :now,
                last_error = NULL,
                updated_at = :now 
            WHERE id = :id
        """)
    else:
        query = text("""
            UPDATE connected_sources 
            SET last_polled_at = :now,
                last_error = :last_error,
                updated_at = :now 
            WHERE id = :id
        """)
    
    params = {"id": source_id, "now": now, "last_error": last_error}
    with engine.begin() as connection:
        connection.execute(query, params)


def is_video_processed(source_id: str, video_id: str) -> bool:
    """Check deduplication history (O(1) lookup)."""
    query = text("""
        SELECT 1 FROM processed_videos 
        WHERE source_id = :source_id AND video_id = :video_id
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {"source_id": source_id, "video_id": video_id}).one_or_none()
    return row is not None


def record_ingestion_atomic(
    *,
    source_id: str,
    user_id: str,
    video_id: str,
    video_url: str,
    brand_kit_id: str | None = None,
    prompt_version: str = "v4",
) -> str:
    """
    ATOMIC TRANSACTION:
    1. Create the job record.
    2. Record the video as processed.
    Returns the new job_id.
    """
    with engine.begin() as connection:
        # Create Job
        job_query = text("""
            INSERT INTO jobs (source_video_url, prompt_version, user_id, brand_kit_id, status)
            VALUES (:url, :v, :u, :bk, 'ingested')
            RETURNING id
        """)
        job_row = connection.execute(job_query, {
            "url": video_url,
            "v": prompt_version,
            "u": user_id,
            "bk": brand_kit_id,
        }).one()
        new_job_id = str(job_row.id)
        
        # Record Processed Video
        history_query = text("""
            INSERT INTO processed_videos (source_id, video_id, job_id)
            VALUES (:sid, :vid, :jid)
        """)
        connection.execute(history_query, {
            "sid": source_id,
            "vid": video_id,
            "jid": new_job_id
        })
        
        return new_job_id


def add_to_publish_queue(
    user_id: str,
    job_id: str,
    clip_index: int,
    platform: str,
    scheduled_for: datetime,
) -> dict:
    """Add a clip to the social media publish queue and initialize performance tracking."""
    # 1. Fetch job to get predicted score
    job = get_job(job_id)
    predicted_score = 0.0
    if job and job.clips_json:
        # Find the clip index in the clips_json list
        def _clip_index(value: Any) -> int:
            data = value.model_dump() if hasattr(value, "model_dump") else dict(value)
            return int(data.get("clip_index", -1))

        clip = next((c for c in job.clips_json if _clip_index(c) == clip_index), None)
        if clip:
            # Aggregate or pick the primary score (virality_score is the best predictor)
            clip_data = clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)
            predicted_score = float(clip_data.get("virality_score", 0.0))

    # 2. Add to queue
    query = text(
        """
        INSERT INTO publish_queue (user_id, job_id, clip_index, platform, scheduled_for, status)
        VALUES (:user_id, :job_id, :clip_index, :platform, :scheduled_for, 'pending')
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": user_id,
                "job_id": job_id,
                "clip_index": clip_index,
                "platform": platform,
                "scheduled_for": scheduled_for,
            },
        ).one()
    
    # 3. Initialize performance record as the "source of truth"
    upsert_clip_performance(
        user_id=user_id,
        job_id=job_id,
        clip_index=clip_index,
        platform=platform,
        ai_predicted_score=predicted_score,
        window_complete=False
    )
    
    return dict(row._mapping)


def get_pending_publish_items() -> list[dict]:
    """Get items in the queue that are due for publishing."""
    query = text(
        """
        SELECT * FROM publish_queue 
        WHERE status = 'pending' AND scheduled_for <= CURRENT_TIMESTAMP
        ORDER BY scheduled_for ASC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query).all()
    return [dict(row._mapping) for row in rows]


def update_publish_status(
    item_id: str,
    status: str,
    platform_url: str | None = None,
    error_message: str | None = None,
) -> None:
    """Update the status of a publish queue item."""
    query = text(
        """
        UPDATE publish_queue 
        SET status = :status, 
            platform_url = :platform_url, 
            error_message = :error_message,
            published_at = CASE WHEN :status = 'published' THEN CURRENT_TIMESTAMP ELSE published_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
        """
    )
    with engine.begin() as connection:
        connection.execute(
            query,
            {
                "id": item_id,
                "status": status,
                "platform_url": platform_url,
                "error_message": error_message,
            },
        )


# ============================================================================
# PERFORMANCE ALERT QUERIES
# ============================================================================

def create_performance_alert(
    user_id: str,
    alert_type: str,
    message: str,
    metadata: dict | None = None
) -> dict | None:
    """Create a performance alert if cooldown allows."""
    # 1. Check cooldown
    check_query = text("""
        SELECT last_alerted_at FROM alert_cooldowns
        WHERE user_id = :user_id AND alert_type = :alert_type
    """)
    
    with engine.begin() as connection:
        last_alert = connection.execute(check_query, {
            "user_id": user_id, 
            "alert_type": alert_type
        }).scalar()
        
        if last_alert:
            from datetime import timezone
            now = datetime.now(timezone.utc)
            # Handle possible naive datetime from DB
            if last_alert.tzinfo is None:
                last_alert = last_alert.replace(tzinfo=timezone.utc)
            
            diff = now - last_alert
            if diff.total_seconds() < 86400: # 24 hour cooldown
                return None

        # 2. Insert alert
        alert_query = text("""
            INSERT INTO performance_alerts (user_id, alert_type, message, metadata_json)
            VALUES (:user_id, :alert_type, :message, :metadata)
            RETURNING *
        """)
        row = connection.execute(alert_query, {
            "user_id": user_id,
            "alert_type": alert_type,
            "message": message,
            "metadata": json.dumps(metadata or {})
        }).fetchone()
        
        # 3. Update cooldown
        cooldown_query = text("""
            INSERT INTO alert_cooldowns (user_id, alert_type, last_alerted_at)
            VALUES (:user_id, :alert_type, NOW())
            ON CONFLICT (user_id, alert_type) DO UPDATE SET last_alerted_at = NOW()
        """)
        connection.execute(cooldown_query, {
            "user_id": user_id,
            "alert_type": alert_type
        })
        
    return dict(row._mapping) if row else None


def get_performance_alerts(user_id: str, unread_only: bool = True, limit: int = 20) -> list[dict]:
    """Fetch recent performance alerts for a user."""
    filter_clause = "AND is_read = FALSE" if unread_only else ""
    query = text(f"""
        SELECT * FROM performance_alerts
        WHERE user_id = :user_id {filter_clause}
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {
            "user_id": user_id,
            "limit": limit
        }).fetchall()
    
    results = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("metadata_json"), str):
            d["metadata"] = json.loads(d["metadata_json"])
        results.append(d)
    return results


def mark_alerts_as_read(user_id: str, alert_ids: list[str] | str = "all") -> int:
    """Mark specific alerts or all alerts as read."""
    if alert_ids == "all":
        query = text("""
            UPDATE performance_alerts SET is_read = TRUE
            WHERE user_id = :user_id AND is_read = FALSE
        """)
        params = {"user_id": user_id}
    else:
        query = text("""
            UPDATE performance_alerts SET is_read = TRUE
            WHERE user_id = :user_id AND id = ANY(:ids)
        """)
        params = {"user_id": user_id, "ids": alert_ids if isinstance(alert_ids, list) else [alert_ids]}
        
    with engine.begin() as connection:
        result = connection.execute(query, params)
        return result.rowcount


# ============================================================================
# DNA INTELLIGENCE QUERIES (Phase 3)
# ============================================================================

def log_dna_shift(
    user_id: str,
    log_type: str,
    reasoning_code: str,
    dimension: str | None = None,
    old_value: float | None = None,
    new_value: float | None = None,
    sample_size: int = 0,
) -> None:
    """Log a historical weight shift or milestone."""
    query = text("""
        INSERT INTO dna_learning_logs (
            user_id, log_type, dimension, old_value, new_value, reasoning_code, sample_size
        ) VALUES (
            :user_id, :log_type, :dimension, :old_val, :new_val, :code, :size
        )
    """)
    with engine.begin() as connection:
        connection.execute(query, {
            "user_id": str(user_id),
            "log_type": log_type,
            "dimension": dimension,
            "old_val": old_value,
            "new_val": new_value,
            "code": reasoning_code,
            "size": sample_size
        })


def get_dna_history(user_id: str, limit: int = 10) -> list[dict]:
    """Retrieve recent learning logs for DNA dashboard."""
    query = text("""
        SELECT * FROM dna_learning_logs
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).all()
    return [dict(row._mapping) for row in rows]


def get_dna_logs_for_summary(user_id: str, days: int = 30, limit: int = 20) -> list[dict]:
    """Retrieve DNA logs within a specific time window for synthesis."""
    query = text("""
        SELECT * FROM dna_learning_logs
        WHERE user_id = :user_id 
        AND created_at >= NOW() - INTERVAL '1 day' * :days
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {
            "user_id": str(user_id),
            "days": days,
            "limit": limit
        }).all()
    return [dict(row._mapping) for row in rows]


def save_executive_summary(user_id: str, summary_text: str, log_ids: list[str]) -> dict:
    """Persist an LLM-generated executive strategy summary."""
    import uuid
    summary_id = str(uuid.uuid4())
    query = text("""
        INSERT INTO dna_executive_summaries (id, user_id, summary_text, context_log_ids)
        VALUES (:id, :u, :t, :ids)
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "id": summary_id,
            "u": str(user_id),
            "t": summary_text,
            "ids": json.dumps(log_ids)
        }).one()
    data = dict(row._mapping)
    data["user_id"] = str(data["user_id"])
    return data


def get_latest_executive_summary(user_id: str) -> dict | None:
    """Retrieve the most recent executive summary for a user."""
    query = text("""
        SELECT * FROM dna_executive_summaries
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 1
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).first()
    
    if not row:
        return None
        
    data = dict(row._mapping)
    if isinstance(data.get("context_log_ids"), str):
        data["context_log_ids"] = json.loads(data["context_log_ids"])
    return data


# ============================================================================
# AUTOPILOT QUERIES (Phase 2 & 4 Restored)
# ============================================================================

def create_connected_source(user_id: str, name: str, source_type: str, config: dict) -> dict:
    """Register a new automated content source (YouTube, RSS)."""
    query = text("""
        INSERT INTO connected_sources (user_id, name, source_type, config_json)
        VALUES (:user_id, :name, :type, :config)
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "name": name,
            "type": source_type,
            "config": json.dumps(config)
        }).one()
    return dict(row._mapping)


def list_active_sources(user_id: str) -> list[dict]:
    """List all sources marked as active for a specific user."""
    query = text("""
        SELECT * FROM connected_sources 
        WHERE user_id = :user_id AND is_active = TRUE 
        ORDER BY created_at DESC
    """)


def get_latest_executive_summary(user_id: str) -> dict | None:
    """Retrieve the most recent executive summary for a user."""

        

# ============================================================================
# PHASE 3: PERFORMANCE & ANALYTICS
# ============================================================================

def upsert_clip_performance(
    user_id: str,
    job_id: str,
    clip_index: int,
    platform: str,
    source_type: str,
    views: int,
    likes: int,
    engagement_score: float,
    performance_delta: float,
    milestone_tier: str | None,
    window_complete: bool,
    synced_at: datetime,
) -> dict:
    """Insert or update performance metrics for a specific clip."""
    query = text("""
        INSERT INTO clip_performance (
            user_id, job_id, clip_index, platform, source_type,
            views, likes, engagement_score, performance_delta,
            milestone_tier, window_complete, synced_at
        ) VALUES (
            :user_id, :job_id, :clip_index, :platform, :source_type,
            :views, :likes, :engagement_score, :performance_delta,
            :milestone_tier, :window_complete, :synced_at
        )
        ON CONFLICT (user_id, job_id, clip_index, platform) DO UPDATE SET
            views = EXCLUDED.views,
            likes = EXCLUDED.likes,
            engagement_score = EXCLUDED.engagement_score,
            performance_delta = EXCLUDED.performance_delta,
            milestone_tier = EXCLUDED.milestone_tier,
            window_complete = EXCLUDED.window_complete,
            synced_at = EXCLUDED.synced_at,
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
            "synced_at": synced_at
        }).one()
    return dict(row._mapping)


def create_performance_alert(
    user_id: str,
    alert_type: str,
    message: str,
    metadata: dict | None = None,
) -> dict:
    """Create a new performance milestone or alert."""
    query = text("""
        INSERT INTO performance_alerts (user_id, alert_type, message, metadata_json)
        VALUES (:user_id, :alert_type, :message, :metadata)
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "alert_type": alert_type,
            "message": message,
            "metadata": json.dumps(metadata or {})
        }).one()
    return dict(row._mapping)


def get_platform_credentials(user_id: str, platform: str) -> dict | None:
    """Retrieve encrypted credentials for a user/platform."""
    query = text("""
        SELECT * FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform
        }).first()
    return dict(row._mapping) if row else None


def save_platform_credentials(
    user_id: str,
    platform: str,
    access_token_encrypted: str,
    refresh_token_encrypted: str,
    expires_at: datetime | None,
    account_id: str | None = None,
    account_name: str | None = None,
    scopes: list[str] | None = None,
) -> dict:
    """Save or update OAuth credentials."""
    query = text("""
        INSERT INTO platform_credentials (
            user_id, platform, access_token_encrypted, refresh_token_encrypted,
            expires_at, account_id, account_name, scopes
        ) VALUES (
            :user_id, :platform, :access, :refresh, :expiry, :acc_id, :acc_name, :scopes
        )
        ON CONFLICT (user_id, platform) DO UPDATE SET
            access_token_encrypted = EXCLUDED.access_token_encrypted,
            refresh_token_encrypted = EXCLUDED.refresh_token_encrypted,
            expires_at = EXCLUDED.expires_at,
            account_id = EXCLUDED.account_id,
            account_name = EXCLUDED.account_name,
            scopes = EXCLUDED.scopes,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
            "access": access_token_encrypted,
            "refresh": refresh_token_encrypted,
            "expiry": expires_at,
            "acc_id": account_id,
            "acc_name": account_name,
            "scopes": ",".join(scopes) if scopes else None
        }).one()
    return dict(row._mapping)


def get_all_users_with_active_platforms() -> list[str]:
    """Retrieve unique user IDs that have at least one active platform connection."""
    query = text("SELECT DISTINCT user_id FROM platform_credentials WHERE is_active = TRUE")
    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()
    return [str(row[0]) for row in rows]


def get_user_performance_summary(user_id: str) -> dict:
    """Aggregate performance metrics for a user's dashboard."""
    query = text("""
        SELECT 
            COUNT(DISTINCT job_id) as total_jobs,
            COUNT(*) as total_clips,
            SUM(views) as total_views,
            SUM(likes) as total_likes,
            AVG(engagement_score) as avg_engagement,
            COUNT(CASE WHEN milestone_tier = 'viral' THEN 1 END) as viral_hits,
            COUNT(CASE WHEN milestone_tier = 'validated' THEN 1 END) as validated_hits
        FROM clip_performance
        WHERE user_id = :user_id
    """)
    
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).fetchone()
        
    if not row or row.total_clips == 0:
        return {
            "total_views": 0, "total_likes": 0, "avg_engagement": 0.0,
            "viral_hits": 0, "validated_hits": 0, "growth_percentage": 0
        }
        
    return {
        "total_views": row.total_views or 0,
        "total_likes": row.total_likes or 0,
        "avg_engagement": round(float(row.avg_engagement or 0.0), 4),
        "viral_hits": row.viral_hits,
        "validated_hits": row.validated_hits,
        "total_clips": row.total_clips
    }


def list_performance_alerts(user_id: str, limit: int = 10) -> list[dict]:
    """Retrieve recent milestone and error alerts for the user."""
    query = text("""
        SELECT * FROM performance_alerts
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "limit": limit}).fetchall()
    
    results = []
    for r in rows:
        d = dict(r._mapping)
        if isinstance(d.get("metadata_json"), str):
            d["metadata"] = json.loads(d["metadata_json"])
        results.append(d)
    return results
