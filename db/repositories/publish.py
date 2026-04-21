"""Publish-related repository helpers."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

from db.connection import engine


def list_platform_accounts(user_id: str) -> list[dict]:
    query = text(
        """
        SELECT *
        FROM platform_credentials
        WHERE user_id = :user_id
        ORDER BY CASE WHEN synced_at IS NULL THEN 1 ELSE 0 END, synced_at DESC, created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    return [dict(row._mapping) for row in rows]


def list_social_accounts(user_id: str) -> list[dict]:
    query = text(
        """
        SELECT *
        FROM social_accounts
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).fetchall()
    return [dict(row._mapping) for row in rows]


def create_published_clip(
    *,
    user_id: str,
    job_id: str,
    clip_index: int,
    platform: str,
    social_account_id: str | None = None,
    caption: str = "",
    hashtags: list[str] | None = None,
    scheduled_at: datetime | None = None,
    published_at: datetime | None = None,
) -> dict:
    query = text(
        """
        INSERT INTO published_clips (
            user_id, job_id, clip_index, platform, social_account_id,
            caption, hashtags, published_at, scheduled_at, status
        )
        VALUES (
            :user_id, :job_id, :clip_index, :platform, :social_account_id,
            :caption, :hashtags, :published_at, :scheduled_at,
            CASE WHEN :published_at IS NOT NULL THEN 'published'
                 WHEN :scheduled_at IS NOT NULL THEN 'scheduled'
                 ELSE 'queued' END
        )
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
                "platform": platform,
                "social_account_id": social_account_id,
                "caption": caption,
                "hashtags": json.dumps(hashtags or []),
                "published_at": published_at,
                "scheduled_at": scheduled_at,
            },
        ).one()
    return dict(row._mapping)


def add_to_publish_queue(
    user_id: str,
    job_id: str,
    clip_index: int,
    platform: str,
    scheduled_for: datetime,
) -> dict:
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
                "user_id": str(user_id),
                "job_id": str(job_id),
                "clip_index": clip_index,
                "platform": platform,
                "scheduled_for": scheduled_for,
            },
        ).one()
    return dict(row._mapping)


def update_publish_status(
    item_id: str,
    status: str,
    platform_url: str | None = None,
    error_message: str | None = None,
) -> None:
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


def get_publish_queue_history(user_id: str, limit: int = 50) -> list[dict]:
    query = text(
        """
        SELECT id, job_id, clip_index, platform, scheduled_for, status, error_message, published_at
        FROM publish_queue
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "limit": limit}).fetchall()
    return [dict(row._mapping) for row in rows]
