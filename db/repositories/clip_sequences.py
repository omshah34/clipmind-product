"""Clip sequence repository functions.

Currently this module proxies shared job/timeline helpers from the jobs
repository and owns persistence helpers for the ``clip_sequences`` table.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine
from db.repositories.jobs import (
    get_job,
    get_job_timeline,
    update_job,
    update_job_timeline,
    append_regeneration_result,
)


def create_clip_sequence(
    *,
    user_id: UUID | str,
    job_id: UUID | str,
    sequence_title: str | None,
    clip_indices: list[int],
    suggested_captions: list[str],
    cliffhanger_scores: list[float],
    series_description: str | None = None,
    platform_optimizations: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Persist a detected narrative sequence and return the inserted row.

    The table stores structured fields as JSON text for both SQLite and
    Postgres compatibility, mirroring the rest of the repository layer.
    """
    query = text(
        """
        INSERT INTO clip_sequences (
            user_id,
            job_id,
            sequence_title,
            clip_indices,
            series_description,
            suggested_captions,
            cliffhanger_scores,
            platform_optimizations
        )
        VALUES (
            :user_id,
            :job_id,
            :sequence_title,
            :clip_indices,
            :series_description,
            :suggested_captions,
            :cliffhanger_scores,
            :platform_optimizations
        )
        RETURNING
            id,
            user_id,
            job_id,
            sequence_title,
            clip_indices,
            series_description,
            suggested_captions,
            cliffhanger_scores,
            platform_optimizations,
            created_at,
            updated_at
        """
    )

    params = {
        "user_id": str(user_id),
        "job_id": str(job_id),
        "sequence_title": sequence_title,
        "clip_indices": json.dumps(clip_indices),
        "series_description": series_description,
        "suggested_captions": json.dumps(suggested_captions),
        "cliffhanger_scores": json.dumps(cliffhanger_scores),
        "platform_optimizations": json.dumps(platform_optimizations or {}),
    }

    with engine.begin() as connection:
        row = connection.execute(query, params).mappings().one_or_none()

    return dict(row) if row else None
