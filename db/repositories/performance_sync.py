"""Persistent sync-job tracking for performance refreshes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def create_performance_sync_job(job_id: str, user_id: UUID | str, status: str = "pending") -> dict[str, Any]:
    query = text(
        """
        INSERT INTO performance_sync_jobs (job_id, user_id, status, error_message, created_at, updated_at)
        VALUES (:job_id, :user_id, :status, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT (job_id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            status = EXCLUDED.status,
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {"job_id": job_id, "user_id": str(user_id), "status": status},
        ).one()
    return dict(row._mapping)


def update_performance_sync_job(
    job_id: str,
    *,
    status: str,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    query = text(
        """
        UPDATE performance_sync_jobs
        SET status = :status,
            error_message = :error_message,
            updated_at = CURRENT_TIMESTAMP
        WHERE job_id = :job_id
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {"job_id": job_id, "status": status, "error_message": error_message},
        ).one_or_none()
    return dict(row._mapping) if row else None


def get_performance_sync_job(job_id: str) -> dict[str, Any] | None:
    query = text("SELECT * FROM performance_sync_jobs WHERE job_id = :job_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"job_id": job_id}).one_or_none()
    return dict(row._mapping) if row else None
