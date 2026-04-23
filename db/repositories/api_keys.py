"""API Key repository functions."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def create_api_key(
    user_id: UUID | str,
    name: str,
    key_hash: str,
    rate_limit_per_min: int = 60,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a new API key for a user."""
    key_prefix = f"clipmind_{secrets.token_hex(6)}"
    
    query = text(
        """
        INSERT INTO api_keys
        (user_id, name, key_prefix, key_hash, rate_limit_per_min, is_active, expires_at)
        VALUES (:user_id, :name, :key_prefix, :key_hash, :rate_limit_per_min, true, :expires_at)
        RETURNING id, key_prefix, name, is_active, rate_limit_per_min, created_at, expires_at
        """
    )
    
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "name": name,
                "key_prefix": key_prefix,
                "key_hash": key_hash,
                "rate_limit_per_min": rate_limit_per_min,
                "expires_at": expires_at,
            },
        ).fetchone()
    
    return dict(row._mapping) if row else None


def get_api_key_by_prefix(key_prefix: str) -> dict[str, Any] | None:
    """Get API key by prefix (for authentication)."""
    query = text(
        """
        SELECT id, user_id, name, key_prefix, key_hash, is_active, rate_limit_per_min, last_used_at
        FROM api_keys WHERE key_prefix = :key_prefix
        """
    )
    
    with engine.connect() as connection:
        row = connection.execute(query, {"key_prefix": key_prefix}).fetchone()
    
    return dict(row._mapping) if row else None


def list_user_api_keys(user_id: UUID | str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    """List all API keys for a user."""
    query = text(
        """
        SELECT id, name, key_prefix, is_active, rate_limit_per_min,
               last_used_at, created_at, expires_at
        FROM api_keys
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit OFFSET :offset
        """
    )
    
    count_query = text("SELECT COUNT(*) FROM api_keys WHERE user_id = :user_id")
    
    with engine.connect() as connection:
        rows = connection.execute(
            query,
            {"user_id": str(user_id), "limit": limit, "offset": offset},
        ).fetchall()
        total = connection.execute(count_query, {"user_id": str(user_id)}).scalar()
    
    return {
        "keys": [dict(row._mapping) for row in rows],
        "total": total,
    }


def revoke_api_key(api_key_id: UUID | str) -> bool:
    """Revoke an API key."""
    query = text("UPDATE api_keys SET is_active = false WHERE id = :id")
    
    with engine.begin() as connection:
        result = connection.execute(query, {"id": str(api_key_id)})
    
    return result.rowcount > 0


def update_api_key_last_used(key_prefix: str) -> None:
    """Update the last_used_at timestamp."""
    query = text(
        "UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE key_prefix = :key_prefix"
    )
    
    with engine.begin() as connection:
        connection.execute(query, {"key_prefix": key_prefix})
