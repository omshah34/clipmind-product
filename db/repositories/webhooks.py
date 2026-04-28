"""Webhook repository functions."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def _serialize_event_types(event_types: list[str]) -> list[str] | str:
    if engine.dialect.name == "sqlite":
        return json.dumps(event_types)
    return event_types


def create_webhook(
    user_id: UUID | str,
    url: str,
    event_types: list[str],
    secret: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """Create a new webhook endpoint."""
    query = text(
        """
        INSERT INTO webhooks
        (user_id, url, event_types, secret, timeout_seconds, is_active)
        VALUES (:user_id, :url, :event_types, :secret, :timeout_seconds, true)
        RETURNING id, user_id, url, event_types, secret, is_active, 
                  timeout_seconds, retry_count, retry_max, created_at, updated_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "url": url,
                "event_types": _serialize_event_types(event_types),
                "secret": secret,
                "timeout_seconds": timeout_seconds,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_webhook(webhook_id: UUID | str) -> dict[str, Any] | None:
    """Get a webhook by ID."""
    query = text(
        """
        SELECT id, user_id, url, event_types, secret, is_active, 
               timeout_seconds, retry_count, retry_max, created_at, updated_at
        FROM webhooks WHERE id = :id AND deleted_at IS NULL
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, {"id": str(webhook_id)}).fetchone()
    
    return dict(row._mapping) if row else None


def list_user_webhooks(user_id: UUID | str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List all webhooks for a user."""
    query = text(
        """
        SELECT id, url, event_types, is_active, timeout_seconds, 
               retry_count, retry_max, created_at, updated_at
        FROM webhooks
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM webhooks WHERE user_id = :user_id AND deleted_at IS NULL")
    
    with engine.begin() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "webhooks": [dict(row._mapping) for row in rows],
        "total": total,
    }


def list_active_webhooks_for_event(event_type: str) -> list[dict[str, Any]]:
    """Get all active webhooks subscribed to an event type."""
    if engine.dialect.name == "sqlite":
        query = text(
            """
            SELECT id, user_id, url, event_types, secret, timeout_seconds
            FROM webhooks
            WHERE is_active = 1 AND deleted_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM json_each(webhooks.event_types)
                  WHERE json_each.value = :event_type
              )
            """
        )
    else:
        query = text(
            """
            SELECT id, user_id, url, event_types, secret, timeout_seconds
            FROM webhooks
            WHERE is_active = true AND deleted_at IS NULL AND :event_type = ANY(event_types)
            """
        )
    
    with engine.begin() as connection:
        rows = connection.execute(query, {"event_type": event_type}).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_webhook(webhook_id: UUID | str, **fields: Any) -> dict[str, Any] | None:
    """Update webhook fields."""
    allowed_fields = {"url", "event_types", "is_active", "timeout_seconds"}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
    
    if not update_fields:
        return get_webhook(webhook_id)
    
    set_clause = ", ".join(f"{k} = :{k}" for k in update_fields.keys())
    query = text(
        f"""
        UPDATE webhooks SET {set_clause}, updated_at = CURRENT_TIMESTAMP
        WHERE id = :id AND deleted_at IS NULL
        RETURNING id, url, event_types, is_active, timeout_seconds, 
                  retry_count, retry_max, created_at, updated_at
        """
    )
    
    params = {"id": str(webhook_id), **update_fields}

    if "event_types" in params:
        params["event_types"] = _serialize_event_types(params["event_types"])
    
    with engine.begin() as connection:
        row = connection.execute(query, params).fetchone()
    
    return dict(row._mapping) if row else None


def delete_webhook(webhook_id: UUID | str) -> bool:
    """Soft-delete a webhook."""
    query_delete = text(
        "UPDATE webhooks SET deleted_at = CURRENT_TIMESTAMP, is_active = false, updated_at = CURRENT_TIMESTAMP WHERE id = :id AND deleted_at IS NULL"
    )
    
    with engine.begin() as connection:
        result = connection.execute(query_delete, {"id": str(webhook_id)})
    
    return result.rowcount > 0


def create_webhook_delivery(
    webhook_id: UUID | str,
    event_type: str,
    event_data: dict,
) -> dict[str, Any]:
    """Create a new webhook delivery record."""
    query = text(
        """
        INSERT INTO webhook_deliveries
        (webhook_id, event_type, event_data, status)
        VALUES (:webhook_id, :event_type, :event_data, 'pending')
        RETURNING id, webhook_id, event_type, status, attempt_count, created_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "webhook_id": str(webhook_id),
                "event_type": event_type,
                "event_data": json.dumps(event_data),
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_pending_webhook_deliveries() -> list[dict[str, Any]]:
    """Get all pending webhook deliveries ready to retry."""
    query = text(
        """
        SELECT id, webhook_id, event_type, event_data, attempt_count, retry_max
        FROM webhook_deliveries
        WHERE status = 'pending' 
          AND (next_retry_at IS NULL OR next_retry_at <= CURRENT_TIMESTAMP)
          AND attempt_count < retry_max
        ORDER BY created_at ASC
        LIMIT 100
        """
    )
    
    with engine.begin() as connection:
        rows = connection.execute(query).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_webhook_delivery(
    delivery_id: UUID | str,
    http_status: int | None = None,
    response_body: str | None = None,
    status: str | None = None,
    error_message: str | None = None,
    next_retry_at: Any = None,
) -> dict[str, Any] | None:
    """Update webhook delivery status after an attempt."""
    query = text(
        """
        UPDATE webhook_deliveries
        SET http_status = COALESCE(:http_status, http_status),
            response_body = COALESCE(:response_body, response_body),
            status = COALESCE(:status, status),
            error_message = COALESCE(:error_message, error_message),
            next_retry_at = COALESCE(:next_retry_at, next_retry_at),
            attempt_count = attempt_count + 1,
            delivered_at = CASE WHEN :status = 'delivered' THEN CURRENT_TIMESTAMP ELSE delivered_at END
        WHERE id = :id
        RETURNING id, webhook_id, status, attempt_count, http_status, delivered_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "id": str(delivery_id),
                "http_status": http_status,
                "response_body": response_body,
                "status": status,
                "error_message": error_message,
                "next_retry_at": next_retry_at,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_webhook_delivery(delivery_id: UUID | str) -> dict[str, Any] | None:
    """Get a webhook delivery record by ID."""
    query = text(
        """
        SELECT id, webhook_id, event_type, event_data, http_status, response_body, 
               status, attempt_count, retry_max, error_message, created_at, 
               delivered_at, next_retry_at
        FROM webhook_deliveries WHERE id = :id
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, {"id": str(delivery_id)}).fetchone()
    
    return dict(row._mapping) if row else None
