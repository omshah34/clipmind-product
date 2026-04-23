"""Job repository functions with persisted transition logging."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.models.job import JobRecord
from db.connection import engine
from db.job_state import record_job_transition

JSON_FIELDS = {"transcript_json", "clips_json", "timeline_json"}
UPDATABLE_FIELDS = {
    "status",
    "source_video_url",
    "proxy_video_url",
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
    "is_rejected",
    "rejected_at",
    "completed_at",
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


def get_job(job_id: UUID | str) -> JobRecord | None:
    query = text("SELECT * FROM jobs WHERE id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": str(job_id)}).one_or_none()
    return _row_to_job_record(row) if row else None


def get_job_timeline(job_id: UUID | str) -> dict | None:
    query = text("SELECT timeline_json FROM jobs WHERE id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": str(job_id)}).one_or_none()
    
    if not row:
        return None
    
    data = row[0]
    if isinstance(data, str):
        try:
            return json.loads(data)
        except json.JSONDecodeError:
            return {}
    return data or {}


def update_job_timeline(job_id: UUID | str, timeline_data: dict) -> JobRecord:
    return update_job(job_id, timeline_json=timeline_data)


def append_regeneration_result(job_id: UUID | str, result: dict) -> dict:
    current_timeline = get_job_timeline(job_id)
    if current_timeline is None:
        current_timeline = {"clips": [], "regeneration_results": []}
    if "regeneration_results" not in current_timeline:
        current_timeline["regeneration_results"] = []
    current_timeline["regeneration_results"].append(result)
    update_job_timeline(job_id, current_timeline)
    return current_timeline


def create_job(
    *,
    user_id: UUID | str,
    source_video_url: str,
    prompt_version: str = "v4",
    brand_kit_id: UUID | str | None = None,
    campaign_id: UUID | str | None = None,
    estimated_cost_usd: float = 0.0,
    status: str = "uploaded",
    language: str | None = "en",
) -> JobRecord:
    columns = [
        "status",
        "source_video_url",
        "prompt_version",
        "estimated_cost_usd",
        "user_id",
        "brand_kit_id",
        "campaign_id",
        "language",
    ]
    values = [
        ":status",
        ":source_video_url",
        ":prompt_version",
        ":estimated_cost_usd",
        ":user_id",
        ":brand_kit_id",
        ":campaign_id",
        ":language",
    ]

    # Gap 33: Use an UPSERT-like pattern to return existing job if it exists
    # This prevents redundant processing of the same video/prompt version.
    query = text(
        f"""
        INSERT INTO jobs (
            {", ".join(columns)}
        )
        VALUES (
            {", ".join(values)}
        )
        ON CONFLICT (user_id, source_video_url, prompt_version) WHERE user_id IS NOT NULL
        DO UPDATE SET updated_at = NOW() -- No-op update to ensure RETURNING * works
        RETURNING *
        """
    )
    
    params = {
        "status": status,
        "source_video_url": source_video_url,
        "prompt_version": prompt_version,
        "estimated_cost_usd": estimated_cost_usd,
        "user_id": str(user_id) if user_id else None,
        "brand_kit_id": str(brand_kit_id) if brand_kit_id else None,
        "campaign_id": str(campaign_id) if campaign_id else None,
        "language": language or "en",
    }

    try:
        with engine.begin() as connection:
            row = connection.execute(query, params).one_or_none()
            
            # If no-user (anonymous) conflict occurs, the above ON CONFLICT won't catch it
            # since it's filtered. We handle anon conflict here.
            if not row and not user_id:
                query_anon = text("""
                    INSERT INTO jobs (status, source_video_url, prompt_version, estimated_cost_usd, language)
                    VALUES (:status, :source_video_url, :prompt_version, :estimated_cost_usd, :language)
                    ON CONFLICT (source_video_url, prompt_version) WHERE user_id IS NULL
                    DO UPDATE SET updated_at = NOW()
                    RETURNING *
                """)
                row = connection.execute(query_anon, params).one()

        if not row:
             # Fallback if both fail (should not happen with logic above)
             raise RuntimeError("Failed to create or retrieve job")

        return _row_to_job_record(row)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error("Database error in create_job: %s", e)
        raise


def update_job(job_id: UUID | str, **fields: Any) -> JobRecord:
    current = get_job(job_id)
    previous_status = current.status if current else None
    assignments: list[str] = []
    params: dict[str, Any] = {"job_id": str(job_id)}

    for field_name, value in fields.items():
        if field_name not in UPDATABLE_FIELDS:
            raise ValueError(f"Unsupported job field: {field_name}")
        assignments.append(f"{field_name} = :{field_name}")
        params[field_name] = json.dumps(value) if field_name in JSON_FIELDS and value is not None else value

    if not assignments:
        if current is None:
            raise ValueError("Job not found")
        return current

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
    new_status = updated.status
    if new_status != previous_status:
        record_job_transition(
            str(job_id),
            previous_status,
            new_status,
            stage=fields.get("status"),
            payload={key: value for key, value in fields.items() if key != "status"},
        )
    return updated


def delete_job(job_id: UUID | str) -> bool:
    """Delete a job by ID from the database."""
    query = text("DELETE FROM jobs WHERE id = :job_id")
    with engine.begin() as connection:
        result = connection.execute(query, {"job_id": str(job_id)})
    return result.rowcount > 0
