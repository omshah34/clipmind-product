"""Persistent job transition event helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from core.request_context import current_context
from db.connection import engine


def record_job_transition(
    job_id: str,
    previous_status: str | None,
    new_status: str,
    *,
    stage: str | None = None,
    payload: dict[str, Any] | None = None,
    source: str | None = None,
) -> dict[str, Any]:
    context = current_context()
    event_source = source or context.source or "system"
    query = text(
        """
        INSERT INTO job_state_events (
            job_id, previous_status, new_status, stage, payload_json,
            source, request_id, user_id, created_at
        )
        VALUES (
            :job_id, :previous_status, :new_status, :stage, :payload_json,
            :source, :request_id, :user_id, CURRENT_TIMESTAMP
        )
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "job_id": str(job_id),
                "previous_status": previous_status,
                "new_status": new_status,
                "stage": stage,
                "payload_json": json.dumps(payload or {}, default=str),
                "source": event_source,
                "request_id": context.request_id,
                "user_id": context.user_id,
            },
        ).one()
    return dict(row._mapping)


def get_job_transition_history(job_id: str, limit: int = 100) -> list[dict[str, Any]]:
    query = text(
        """
        SELECT *
        FROM job_state_events
        WHERE job_id = :job_id
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"job_id": str(job_id), "limit": limit}).fetchall()
    return [dict(row._mapping) for row in rows]


def get_latest_job_transition(job_id: str) -> dict[str, Any] | None:
    history = get_job_transition_history(job_id, limit=1)
    return history[0] if history else None
