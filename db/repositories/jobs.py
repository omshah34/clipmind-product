"""Job repository functions with persisted transition logging."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from api.models.job import JobRecord
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
    return row[0] if row else None


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
    estimated_cost_usd: float = 0.0,
    status: str = "uploaded",
) -> JobRecord:
    columns = [
        "status",
        "source_video_url",
        "prompt_version",
        "estimated_cost_usd",
        "user_id",
        "brand_kit_id",
        "language",
    ]
    values = [
        ":status",
        ":source_video_url",
        ":prompt_version",
        ":estimated_cost_usd",
        ":user_id",
        ":brand_kit_id",
        ":language",
    ]

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
        row = connection.execute(
            query,
            {
                "status": status,
                "source_video_url": source_video_url,
                "prompt_version": prompt_version,
                "estimated_cost_usd": estimated_cost_usd,
                "user_id": str(user_id) if user_id else None,
                "brand_kit_id": str(brand_kit_id) if brand_kit_id else None,
                "language": "en",
            },
        ).one()
    return _row_to_job_record(row)


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
