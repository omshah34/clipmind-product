from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from api.models.job import JobRecord
from db.connection import engine


JSON_FIELDS = {"transcript_json", "clips_json"}
UPDATABLE_FIELDS = {
    "status",
    "source_video_url",
    "audio_url",
    "transcript_json",
    "clips_json",
    "failed_stage",
    "error_message",
    "retry_count",
    "prompt_version",
    "estimated_cost_usd",
    "actual_cost_usd",
}


def _row_to_job_record(row: Any) -> JobRecord:
    return JobRecord.model_validate(dict(row._mapping))


def create_job(
    *,
    source_video_url: str,
    prompt_version: str,
    estimated_cost_usd: float,
) -> JobRecord:
    query = text(
        """
        INSERT INTO jobs (
            source_video_url,
            prompt_version,
            estimated_cost_usd
        )
        VALUES (
            :source_video_url,
            :prompt_version,
            :estimated_cost_usd
        )
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "source_video_url": source_video_url,
                "prompt_version": prompt_version,
                "estimated_cost_usd": estimated_cost_usd,
            },
        ).one()
    return _row_to_job_record(row)


def get_job(job_id: UUID | str) -> JobRecord | None:
    query = text("SELECT * FROM jobs WHERE id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": str(job_id)}).one_or_none()
    return _row_to_job_record(row) if row else None


def update_job(job_id: UUID | str, **fields: Any) -> JobRecord:
    assignments: list[str] = []
    params: dict[str, Any] = {"job_id": str(job_id)}

    for field_name, value in fields.items():
        if field_name not in UPDATABLE_FIELDS:
            raise ValueError(f"Unsupported job field: {field_name}")
        if field_name in JSON_FIELDS:
            assignments.append(f"{field_name} = CAST(:{field_name} AS JSONB)")
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
    return _row_to_job_record(row)
