"""Job repository functions with persisted transition logging."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.models.job import JobRecord
from db.connection import engine
from db.job_state import record_job_transition
from db.repositories.clips import insert_clip_rows

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


def get_job(job_id: UUID | str, user_id: UUID | str | None = None) -> JobRecord | None:
    if user_id:
        query = text("SELECT * FROM jobs WHERE id = :job_id AND user_id = :user_id")
        params = {"job_id": str(job_id), "user_id": str(user_id)}
    else:
        query = text("SELECT * FROM jobs WHERE id = :job_id")
        params = {"job_id": str(job_id)}
        
    with engine.connect() as connection:
        row = connection.execute(query, params).one_or_none()
    return _row_to_job_record(row) if row else None


def list_jobs_for_user(
    user_id: UUID | str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    query = text(
        """
        SELECT id, status, source_video_url, failed_stage, error_message, language, completed_at, created_at, updated_at
        FROM jobs
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    count_query = text("SELECT COUNT(*) FROM jobs WHERE user_id = :user_id")
    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = int(connection.execute(count_query, {"user_id": str(user_id)}).scalar() or 0)
    return [dict(row._mapping) for row in rows], total


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
    # Always generate the ID in Python so we never rely on the DB DEFAULT.
    # This is critical for SQLite where the old schema had DEFAULT NULL.
    new_id = str(uuid4())

    columns = [
        "id",
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
        ":id",
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
    _ts = "NOW()" if engine.dialect.name == "postgresql" else "CURRENT_TIMESTAMP"
    query = text(
        f"""
        INSERT INTO jobs (
            {", ".join(columns)}
        )
        VALUES (
            {", ".join(values)}
        )
        ON CONFLICT (user_id, source_video_url, prompt_version) WHERE user_id IS NOT NULL
        DO UPDATE SET 
            status = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN EXCLUDED.status ELSE jobs.status END,
            error_message = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN NULL ELSE jobs.error_message END,
            failed_stage = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN NULL ELSE jobs.failed_stage END,
            updated_at = {_ts}
        RETURNING *
        """
    )

    params = {
        "id": new_id,
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
                query_anon = text(f"""
                    INSERT INTO jobs (id, status, source_video_url, prompt_version, estimated_cost_usd, language)
                    VALUES (:id, :status, :source_video_url, :prompt_version, :estimated_cost_usd, :language)
                    ON CONFLICT (source_video_url, prompt_version) WHERE user_id IS NULL
                    DO UPDATE SET 
                        status = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN EXCLUDED.status ELSE jobs.status END,
                        error_message = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN NULL ELSE jobs.error_message END,
                        failed_stage = CASE WHEN jobs.status IN ('failed', 'cancelled') THEN NULL ELSE jobs.failed_stage END,
                        updated_at = {_ts}
                    RETURNING *
                """)
                row = connection.execute(query_anon, params).one()

        if not row:
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

    # Gap 178: Cleanup old files if URLs are updated
    old_urls = []
    if current:
        for field in ["source_video_url", "proxy_video_url", "audio_url"]:
            if field in fields and getattr(current, field) and fields[field] != getattr(current, field):
                old_urls.append(getattr(current, field))

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

    # Best-effort cleanup of old files
    if old_urls:
        import os
        from urllib.parse import urlparse, unquote
        for url in old_urls:
            if url.startswith("file://"):
                try:
                    p_str = unquote(urlparse(url).path)
                    if os.name == "nt" and p_str.startswith("/") and ":" in p_str[1:3]:
                        p_str = p_str.lstrip("/")
                    p = Path(p_str)
                    if p.exists():
                        p.unlink()
                except Exception:
                    pass

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


def normalize_clip_indices(job_id: UUID | str) -> JobRecord | None:
    """Gap 179: Re-sequence clip_index values after a clip is removed.

    When a clip is discarded (e.g. rejected) the remaining clips may have
    non-contiguous indices (0, 2, 3, ...).  Deep links that encode
    ``clip_index`` in the URL will silently point to the wrong clip after
    any earlier clip is removed.

    This function rewrites ``clips_json`` so that the ``clip_index`` field
    on every clip equals its position in the list (0-based, contiguous).
    It is called automatically after any operation that removes a clip.

    Returns the updated JobRecord, or None if the job does not exist.
    """
    job = get_job(job_id)
    if not job or not job.clips_json:
        return job

    # Re-assign clip_index to match list position
    normalised = []
    for new_idx, clip in enumerate(job.clips_json):
        entry = clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)
        entry["clip_index"] = new_idx
        normalised.append(entry)

    return update_job(job_id, clips_json=normalised)

def complete_job_atomic(job_id: UUID | str, clips: list[dict], actual_cost: float) -> JobRecord:
    """
    Gap 210: Atomic Completion.
    Updates job status to 'completed' and inserts clip rows in a single transaction.
    Legacy clips_json is updated outside the transaction for decoupled dual-write.
    """
    from datetime import datetime, timezone
    
    query_job = text("""
        UPDATE jobs 
        SET status = 'completed',
            actual_cost_usd = :cost,
            completed_at = :ts,
            updated_at = :ts
        WHERE id = :job_id
        RETURNING *
    """)
    
    ts = datetime.now(timezone.utc)
    params = {
        "job_id": str(job_id),
        "cost": round(actual_cost, 6),
        "ts": ts
    }

    # 1. Atomic Path: Table insertion + Status update
    with engine.begin() as conn:
        # Update status first
        row = conn.execute(query_job, params).one()
        # Insert clips into relational table
        insert_clip_rows(conn, str(job_id), clips)
    
    # 2. Legacy Path: Dual-write to clips_json (best effort, outside transaction)
    try:
        update_job(job_id, clips_json=clips)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Legacy dual-write failed for job %s: %s", job_id, exc)

    updated = _row_to_job_record(row)
    record_job_transition(
        str(job_id),
        "processing", # Assumption: previous status was processing
        "completed",
        stage="completion",
        payload={"clips_count": len(clips)}
    )
    return updated
