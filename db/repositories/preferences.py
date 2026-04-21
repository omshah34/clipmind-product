"""User preference repository helpers."""

from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def get_user_preferences(user_id: UUID | str) -> dict | None:
    query = text(
        """
        SELECT * FROM user_preferences WHERE user_id = :user_id
        """
    )
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()
    if not row:
        return None
    data = dict(row._mapping)
    if isinstance(data.get("goals"), str):
        try:
            data["goals"] = json.loads(data["goals"])
        except json.JSONDecodeError:
            data["goals"] = []
    if isinstance(data.get("preferences_json"), str):
        try:
            data["preferences_json"] = json.loads(data["preferences_json"])
        except json.JSONDecodeError:
            data["preferences_json"] = {}
    return data


def save_user_preferences(
    user_id: UUID | str,
    *,
    goals: list[str] | None = None,
    target_platform: str | None = None,
    preferences: dict | None = None,
    onboarding_completed: bool = True,
) -> dict:
    query = text(
        """
        INSERT INTO user_preferences (
            user_id, goals, target_platform, preferences_json, onboarding_completed
        ) VALUES (
            :user_id, :goals, :target_platform, :preferences_json, :onboarding_completed
        )
        ON CONFLICT (user_id) DO UPDATE SET
            goals = :goals,
            target_platform = :target_platform,
            preferences_json = :preferences_json,
            onboarding_completed = :onboarding_completed,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *
        """
    )
    payload = {
        "user_id": str(user_id),
        "goals": json.dumps(goals or []),
        "target_platform": target_platform,
        "preferences_json": json.dumps(preferences or {}),
        "onboarding_completed": onboarding_completed,
    }
    with engine.begin() as connection:
        row = connection.execute(query, payload).one()
    return dict(row._mapping)

