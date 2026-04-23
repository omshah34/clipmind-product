"""Source ingestion repository functions."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def record_ingestion_atomic(
    *,
    source_id: str | UUID,
    user_id: str | UUID,
    video_id: str,
    video_url: str,
    brand_kit_id: str | UUID | None = None,
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
            "u": str(user_id),
            "bk": str(brand_kit_id) if brand_kit_id else None,
        }).one()
        new_job_id = str(job_row.id)
        
        # Record Processed Video
        history_query = text("""
            INSERT INTO processed_videos (source_id, video_id, job_id)
            VALUES (:sid, :vid, :jid)
        """)
        connection.execute(history_query, {
            "sid": str(source_id),
            "vid": video_id,
            "jid": new_job_id
        })
        
        return new_job_id
