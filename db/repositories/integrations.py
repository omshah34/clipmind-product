"""Integration repository functions."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def _serialize_trigger_events(trigger_events: list[str]) -> list[str] | str:
    if engine.dialect.name == "sqlite":
        return json.dumps(trigger_events)
    return trigger_events


def create_integration(
    user_id: UUID | str,
    integration_type: str,
    name: str,
    config: dict,
    trigger_events: list[str],
) -> dict[str, Any]:
    """Create a new integration for a user."""
    query = text(
        """
        INSERT INTO integrations (user_id, integration_type, name, config, trigger_events)
        VALUES (:user_id, :integration_type, :name, :config, :trigger_events)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "integration_type": integration_type,
                "name": name,
                "config": json.dumps(config),
                "trigger_events": _serialize_trigger_events(trigger_events),
            },
        ).one()
    return dict(row._mapping)


def get_integration(integration_id: UUID | str) -> dict[str, Any] | None:
    """Get a single integration by ID."""
    query = text("SELECT * FROM integrations WHERE id = :id AND deleted_at IS NULL")
    with engine.connect() as connection:
        row = connection.execute(query, {"id": str(integration_id)}).one_or_none()
    return dict(row._mapping) if row else None


def list_user_integrations(
    user_id: UUID | str,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """List all integrations for a user."""
    query = text(
        """
        SELECT id, integration_type, name, trigger_events, is_active,
               last_triggered_at, created_at, updated_at
        FROM integrations
        WHERE user_id = :user_id AND deleted_at IS NULL
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM integrations WHERE user_id = :user_id AND deleted_at IS NULL")
    
    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "integrations": [dict(row._mapping) for row in rows],
        "total": total,
    }


def list_active_integrations_for_event(event_type: str, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get all active integrations subscribed to an event type.
    Optionally filter by user_id.
    """
    filter_user = " AND user_id = :user_id" if user_id else ""
    if engine.dialect.name == "sqlite":
        query = text(
            f"""
            SELECT id, user_id, integration_type, name, trigger_events, config
            FROM integrations
            WHERE is_active = 1 AND deleted_at IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM json_each(integrations.trigger_events)
                  WHERE json_each.value = :event_type
              ){filter_user}
            """
        )
    else:
        query = text(
            f"""
            SELECT id, user_id, integration_type, name, trigger_events, config
            FROM integrations
            WHERE is_active = true AND deleted_at IS NULL AND :event_type = ANY(trigger_events) {filter_user}
            """
        )
    
    params = {"event_type": event_type}
    if user_id:
        params["user_id"] = str(user_id)
        
    with engine.connect() as connection:
        rows = connection.execute(query, params).fetchall()
    
    return [dict(row._mapping) for row in rows]


def update_integration(integration_id: UUID | str, **fields: Any) -> dict[str, Any] | None:
    """Update integration fields."""
    allowed_fields = {"name", "trigger_events", "is_active", "config"}
    update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
    
    if not update_fields:
        return get_integration(integration_id)
    
    assignments = []
    params = {"id": str(integration_id)}
    
    for field, value in update_fields.items():
        if field == "config" and isinstance(value, dict):
            assignments.append(f"{field} = :{field}")
            params[field] = json.dumps(value)
        elif field == "trigger_events":
            assignments.append(f"{field} = :{field}")
            params[field] = _serialize_trigger_events(value)
        else:
            assignments.append(f"{field} = :{field}")
            params[field] = value
    
    assignments.append("updated_at = CURRENT_TIMESTAMP")
    
    query = text(
        f"""
        UPDATE integrations SET {", ".join(assignments)}
        WHERE id = :id AND deleted_at IS NULL
        RETURNING id, integration_type, name, trigger_events, config,
                  is_active, last_triggered_at, created_at, updated_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(query, params).fetchone()
    
    return dict(row._mapping) if row else None


def delete_integration(integration_id: UUID | str) -> bool:
    """Soft-delete an integration."""
    query = text(
        "UPDATE integrations SET deleted_at = CURRENT_TIMESTAMP, is_active = false, updated_at = CURRENT_TIMESTAMP WHERE id = :id AND deleted_at IS NULL"
    )
    
    with engine.begin() as connection:
        result = connection.execute(query, {"id": str(integration_id)})
    
    return result.rowcount > 0


def update_integration_last_triggered(integration_id: UUID | str) -> None:
    """Update the last_triggered_at timestamp for an integration."""
    query = text(
        "UPDATE integrations SET last_triggered_at = CURRENT_TIMESTAMP WHERE id = :id AND deleted_at IS NULL"
    )
    
    with engine.begin() as connection:
        connection.execute(query, {"id": str(integration_id)})
