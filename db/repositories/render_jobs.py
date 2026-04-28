"""Render job repository functions."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def create_render_job(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    edited_srt: str,
    caption_style: dict | None = None,
    render_recipe: dict | None = None,
) -> dict[str, Any] | None:
    """Create a render job for edited captions."""
    query = text("""
        INSERT INTO render_jobs (
            user_id, job_id, clip_index, edited_srt, edited_style, render_recipe_json, status, progress_percent
        ) VALUES (
            :user_id, :job_id, :clip_index, :edited_srt, :edited_style, :render_recipe_json, 'queued', 0
        )
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "job_id": str(job_id),
            "clip_index": clip_index,
            "edited_srt": edited_srt,
            "edited_style": json.dumps(caption_style or {}),
            "render_recipe_json": json.dumps(render_recipe or {}),
        }).fetchone()
    
    if not row:
        return None
    payload = dict(row._mapping)
    for field_name in ("edited_style", "render_recipe_json"):
        if isinstance(payload.get(field_name), str):
            try:
                payload[field_name] = json.loads(payload[field_name])
            except json.JSONDecodeError:
                pass
    return payload


def get_render_job(render_job_id: UUID | str) -> dict[str, Any] | None:
    """Get render job details."""
    query = text("""
        SELECT * FROM render_jobs WHERE id = :render_job_id
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {"render_job_id": str(render_job_id)}).fetchone()
    
    if not row:
        return None
    payload = dict(row._mapping)
    for field_name in ("edited_style", "render_recipe_json"):
        if isinstance(payload.get(field_name), str):
            try:
                payload[field_name] = json.loads(payload[field_name])
            except json.JSONDecodeError:
                pass
    return payload


def list_render_jobs(
    job_id: UUID | str,
    limit: int = 50,
) -> list[dict[str, Any]]:
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
    
    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row._mapping)
        for field_name in ("edited_style", "render_recipe_json"):
            if isinstance(payload.get(field_name), str):
                try:
                    payload[field_name] = json.loads(payload[field_name])
                except json.JSONDecodeError:
                    pass
        payloads.append(payload)
    return payloads


def update_render_job_status(
    render_job_id: UUID | str,
    status: str,
    progress_percent: int | None = None,
    output_url: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Update render job status."""
    query = text("""
        UPDATE render_jobs SET
            status = :status,
            progress_percent = COALESCE(:progress_percent, progress_percent),
            output_url = COALESCE(:output_url, output_url),
            error_message = COALESCE(:error_message, error_message),
            completed_at = CASE WHEN :status = 'completed' OR :status = 'failed'
                          THEN CURRENT_TIMESTAMP ELSE completed_at END
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
    
    if not row:
        return None
    payload = dict(row._mapping)
    for field_name in ("edited_style", "render_recipe_json"):
        if isinstance(payload.get(field_name), str):
            try:
                payload[field_name] = json.loads(payload[field_name])
            except json.JSONDecodeError:
                pass
    return payload
