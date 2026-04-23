"""User repository functions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def get_user_id_by_email(email: str) -> str | None:
    """Retrieve user ID by email."""
    query = text("SELECT id FROM users WHERE email = :email")
    with engine.connect() as connection:
        result = connection.execute(query, {"email": email}).scalar()
    return str(result) if result else None


def get_all_users_with_active_platforms() -> list[str]:
    """Retrieve unique user IDs that have at least one active platform connection."""
    query = text("SELECT DISTINCT user_id FROM platform_credentials WHERE is_active = TRUE")
    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()
    return [str(row[0]) for row in rows]


def get_user_performance_summary(user_id: str | UUID) -> dict[str, Any]:
    """Aggregate performance metrics for a user's dashboard."""
    query = text("""
        SELECT 
            COUNT(DISTINCT job_id) as total_jobs,
            COUNT(*) as total_clips,
            SUM(views) as total_views,
            SUM(likes) as total_likes,
            AVG(engagement_score) as avg_engagement,
            COUNT(CASE WHEN milestone_tier = 'viral' THEN 1 END) as viral_hits,
            COUNT(CASE WHEN milestone_tier = 'validated' THEN 1 END) as validated_hits
        FROM clip_performance
        WHERE user_id = :user_id
    """)
    
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).fetchone()
        
    if not row or row.total_clips == 0:
        return {
            "total_views": 0, 
            "total_likes": 0, 
            "avg_engagement": 0.0,
            "viral_hits": 0, 
            "validated_hits": 0, 
            "total_clips": 0,
            "total_jobs": 0
        }
        
    return {
        "total_views": row.total_views or 0,
        "total_likes": row.total_likes or 0,
        "avg_engagement": round(float(row.avg_engagement or 0.0), 4),
        "viral_hits": row.viral_hits,
        "validated_hits": row.validated_hits,
        "total_clips": row.total_clips,
        "total_jobs": row.total_jobs
    }


def save_platform_credentials(
    user_id: UUID | str,
    platform: str,
    access_token_encrypted: str,
    account_id: str,
    account_name: str,
    scopes: list[str],
    refresh_token_encrypted: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Save or update platform credentials for API syncing."""
    query = text("""
        INSERT INTO platform_credentials (
            user_id, platform, access_token_encrypted, refresh_token_encrypted,
            expires_at, account_id, account_name, scopes, is_active
        ) VALUES (
            :user_id, :platform, :access_token_encrypted, :refresh_token_encrypted,
            :expires_at, :account_id, :account_name, :scopes, true
        )
        ON CONFLICT (user_id, platform)
        DO UPDATE SET
            access_token_encrypted = :access_token_encrypted,
            refresh_token_encrypted = :refresh_token_encrypted,
            expires_at = :expires_at,
            account_id = :account_id,
            account_name = :account_name,
            scopes = :scopes,
            is_active = true,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
    """)
    
    with engine.begin() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
            "access_token_encrypted": access_token_encrypted,
            "refresh_token_encrypted": refresh_token_encrypted,
            "expires_at": expires_at,
            "account_id": account_id,
            "account_name": account_name,
            "scopes": ','.join(scopes) if isinstance(scopes, list) else scopes,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def get_platform_credentials(
    user_id: UUID | str,
    platform: str,
) -> dict[str, Any] | None:
    """Get platform credentials for a user."""
    query = text("""
        SELECT * FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
    """)
    
    with engine.connect() as connection:
        row = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
        }).fetchone()
    
    return dict(row._mapping) if row else None


def deactivate_platform_credentials(user_id: UUID | str, platform: str, error: str | None = None) -> None:
    """Deactivate credentials after a failed auth attempt."""
    query = text("""
        UPDATE platform_credentials 
        SET is_active = false, last_error = :error, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id AND platform = :platform
    """)
    with engine.begin() as connection:
        connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
            "error": error
        })


def get_user_credits(user_id: str | UUID) -> float:
    """Retrieve user's current credit balance for plan enforcement (Gap 74)."""
    query = text("SELECT mock_credit_balance FROM users WHERE id = :id")
    with engine.connect() as connection:
        res = connection.execute(query, {"id": str(user_id)}).scalar()
    return float(res) if res is not None else 0.0
