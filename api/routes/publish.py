"""Publish workflow endpoints matching the frontend publish page contract."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.dependencies import AuthenticatedUser, get_current_user
from services.publishing_service import publishing_service

router = APIRouter(prefix="/publish", tags=["publish"])


class OptimizeCaptionsPayload(BaseModel):
    original_caption: str
    platforms: list[str] = Field(default_factory=list)


class PublishPayload(BaseModel):
    platform: str
    caption: str
    hashtags: Any = None
    scheduled_for: datetime | None = None


@router.get("/accounts")
def get_accounts(user: AuthenticatedUser = Depends(get_current_user)) -> list[dict]:
    return publishing_service.list_connected_accounts(str(user.user_id))


@router.post("/{job_id}/{clip_index}/optimize-captions")
def optimize_captions(
    job_id: str,
    clip_index: int,
    payload: OptimizeCaptionsPayload,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    job_id_str = str(job_id)
    return publishing_service.optimize_caption(
        str(user.user_id),
        job_id_str,
        clip_index,
        payload.original_caption,
        payload.platforms,
    )


@router.post("/{job_id}/{clip_index}/publish")
def publish_clip(
    job_id: str,
    clip_index: int,
    payload: PublishPayload,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    try:
        return publishing_service.publish_clip(
            user_id=str(user.user_id),
            job_id=str(job_id),
            clip_index=clip_index,
            platform=payload.platform,
            caption=payload.caption,
            hashtags=payload.hashtags,
            scheduled_for=payload.scheduled_for,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

