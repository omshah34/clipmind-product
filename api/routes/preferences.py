"""File: api/routes/preferences.py
Purpose: Persist onboarding and creator preference data.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.dependencies import AuthenticatedUser, get_current_user
from db.repositories.preferences import get_user_preferences, save_user_preferences

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferenceUpdate(BaseModel):
    goals: list[str] = Field(default_factory=list)
    target_platform: str | None = None
    primary_goal: str | None = None
    metadata: dict = Field(default_factory=dict)
    onboarding_completed: bool = True


@router.get("/")
def read_preferences(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    preferences = get_user_preferences(user.user_id) or {}
    return {"preferences": preferences}


@router.put("/")
def update_preferences(
    payload: PreferenceUpdate,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    saved = save_user_preferences(
        user.user_id,
        goals=payload.goals,
        target_platform=payload.target_platform,
        preferences={
            "primary_goal": payload.primary_goal,
            **payload.metadata,
        },
        onboarding_completed=payload.onboarding_completed,
    )
    return {"preferences": saved}
