"""User repository functions."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine
from db.repositories.jobs import get_job
from db.repositories.performance import build_performance_summary


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


def get_user_performance_summary(
    user_id: str | UUID,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Aggregate performance metrics for a user's dashboard."""
    conditions = ["user_id = :user_id"]
    params: dict[str, Any] = {"user_id": str(user_id)}
    if start_date is not None:
        conditions.append("synced_at >= :start_date")
        params["start_date"] = start_date
    if end_date is not None:
        conditions.append("synced_at <= :end_date")
        params["end_date"] = end_date

    query = text(
        f"""
        SELECT *
        FROM clip_performance
        WHERE {" AND ".join(conditions)}
        ORDER BY synced_at DESC, created_at DESC, clip_index ASC
        """
    )

    with engine.connect() as connection:
        rows = connection.execute(query, params).fetchall()

    if not rows:
        summary = build_performance_summary(
            job_id="00000000-0000-0000-0000-000000000000",
            rows=[],
            top_clips=[],
            latest_job_id=None,
            data_source="mock",
        )
        summary["avg_engagement"] = 0.0
        summary["viral_hits"] = 0
        summary["validated_hits"] = 0
        return summary

    latest_job_id = str(rows[0]._mapping["job_id"]) if rows[0]._mapping.get("job_id") else None
    latest_job = get_job(latest_job_id) if latest_job_id else None
    top_clips = getattr(latest_job, "clips_json", None) if latest_job else None
    summary = build_performance_summary(
        job_id=latest_job_id or "00000000-0000-0000-0000-000000000000",
        rows=rows,
        top_clips=top_clips,
        latest_job_id=latest_job_id,
        data_source="real" if any(row._mapping.get("source_type") == "real" for row in rows) else "mock",
    )
    summary["total_jobs"] = len({str(row._mapping["job_id"]) for row in rows if row._mapping.get("job_id")})
    summary["avg_engagement"] = summary["overall_engagement_score"]
    summary["viral_hits"] = sum(1 for row in rows if row._mapping.get("milestone_tier") == "viral")
    summary["validated_hits"] = sum(1 for row in rows if row._mapping.get("milestone_tier") == "validated")
    return summary


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


def delete_platform_credentials(user_id: UUID | str, platform: str) -> bool:
    """Delete stored platform credentials for a user."""
    query = text("""
        DELETE FROM platform_credentials
        WHERE user_id = :user_id AND platform = :platform
    """)
    with engine.begin() as connection:
        result = connection.execute(query, {
            "user_id": str(user_id),
            "platform": platform,
        })
    return result.rowcount > 0


def list_active_users() -> list[dict]:
    """Return all users that have at least one active platform credential.

    Used by the DNA executive-summary Celery task to fan out per-user jobs.
    Each dict contains at minimum ``id``, ``email``, and ``full_name``.
    """
    query = text(
        """
        SELECT DISTINCT u.id, u.email, u.full_name
        FROM users u
        INNER JOIN platform_credentials pc ON pc.user_id = u.id
        WHERE pc.is_active = TRUE
        ORDER BY u.id
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query).fetchall()
    return [dict(row._mapping) for row in rows]


def get_user_credits(user_id: str | UUID) -> float:
    """Retrieve user's current credit balance for plan enforcement (Gap 74)."""
    query = text("SELECT mock_credit_balance FROM users WHERE id = :id")
    with engine.connect() as connection:
        res = connection.execute(query, {"id": str(user_id)}).scalar()
    return float(res) if res is not None else 0.0
