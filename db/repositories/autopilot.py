"""Autopilot repository functions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def create_connected_source(
    user_id: str | UUID,
    name: str,
    source_type: str,
    config: dict,
) -> dict[str, Any]:
    """Create a new automated source for video ingestion."""
    query = text(
        """
        INSERT INTO connected_sources (user_id, name, source_type, config_json)
        VALUES (:user_id, :name, :source_type, :config)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "source_type": source_type,
                "config": json.dumps(config),
            },
        ).one()
    
    data = dict(row._mapping)
    if isinstance(data.get("config_json"), str):
        try:
            data["config_json"] = json.loads(data["config_json"])
        except json.JSONDecodeError:
            data["config_json"] = {}
    return data


def list_active_sources(user_id: str | UUID) -> list[dict[str, Any]]:
    """List active automated sources for a specific user."""
    query = text(
        "SELECT * FROM connected_sources WHERE user_id = :user_id AND is_active = true"
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).all()
    
    results = []
    for row in rows:
        data = dict(row._mapping)
        if isinstance(data.get("config_json"), str):
            try:
                data["config_json"] = json.loads(data["config_json"])
            except json.JSONDecodeError:
                data["config_json"] = {}
        results.append(data)
    return results


def list_active_sources_for_polling() -> list[dict[str, Any]]:
    """Get all enabled sources across the platform for polling."""
    query = text("SELECT * FROM connected_sources WHERE is_active = true")
    with engine.connect() as connection:
        rows = connection.execute(query).all()
    
    results = []
    for row in rows:
        data = dict(row._mapping)
        if isinstance(data.get("config_json"), str):
            try:
                data["config_json"] = json.loads(data["config_json"])
            except json.JSONDecodeError:
                data["config_json"] = {}
        results.append(data)
    return results


def update_source_status(
    source_id: str | UUID, 
    last_error: str | None = None,
    success: bool = False
) -> None:
    """Track polling health."""
    now = datetime.now()
    if success:
        query = text("""
            UPDATE connected_sources 
            SET last_polled_at = :now, 
                last_success_at = :now,
                last_error = NULL,
                updated_at = :now 
            WHERE id = :id
        """)
    else:
        query = text("""
            UPDATE connected_sources 
            SET last_polled_at = :now,
                last_error = :last_error,
                updated_at = :now 
            WHERE id = :id
        """)
    
    params = {"id": str(source_id), "now": now, "last_error": last_error}
    with engine.begin() as connection:
        connection.execute(query, params)


def is_video_processed(source_id: str | UUID, video_id: str) -> bool:
    """Check deduplication history."""
    query = text("""
        SELECT 1 FROM processed_videos 
        WHERE source_id = :source_id AND video_id = :video_id
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {"source_id": str(source_id), "video_id": video_id}).one_or_none()
    return row is not None


def mark_video_as_processed(source_id: str | UUID, video_id: str) -> None:
    """Record a video as processed to avoid duplicates."""
    query = text("""
        INSERT INTO processed_videos (source_id, video_id)
        VALUES (:source_id, :video_id)
        ON CONFLICT DO NOTHING
    """)
    with engine.begin() as connection:
        connection.execute(query, {"source_id": str(source_id), "video_id": video_id})


def get_pending_publish_items(user_id: str | UUID | None = None) -> list[dict[str, Any]]:
    """Get clips scheduled for publishing that are ready."""
    now = datetime.now()
    user_filter = " AND user_id = :user_id" if user_id else ""
    query = text(
        f"""
        SELECT * FROM publish_queue 
        WHERE status = 'pending' AND scheduled_for <= :now {user_filter}
        """
    )
    params = {"now": now}
    if user_id:
        params["user_id"] = str(user_id)
        
    with engine.connect() as connection:
        rows = connection.execute(query, params).all()
    return [dict(row._mapping) for row in rows]


def update_publish_status(
    item_id: str | UUID,
    status: str,
    platform_url: str | None = None,
    error_message: str | None = None
) -> None:
    """Update status of a scheduled publish item."""
    query = text("""
        UPDATE publish_queue 
        SET status = :status, 
            platform_url = :url, 
            error_message = :err,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = :id
    """)
    with engine.begin() as connection:
        connection.execute(query, {
            "id": str(item_id),
            "status": status,
            "url": platform_url,
            "err": error_message
        })
