"""Social media publishing endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.dependencies.auth import AuthenticatedUser, get_current_user
from api.models.social_publish import PublishRequest, PublishStatusResponse
from services.publishing_service import publishing_service

router = APIRouter(prefix="/social-publish", tags=["social_publish"])


@router.post("/schedule")
def schedule_clip(
    request: PublishRequest,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    return publishing_service.schedule_multi_platform_publish(
        user_id=str(user.user_id),
        job_id=str(request.job_id),
        clip_index=request.clip_index,
        platforms=request.platforms,
        caption=request.caption,
        hashtags=request.hashtags,
        scheduled_for=request.scheduled_at,
    )


@router.get("/history")
def list_publish_history(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    # The canonical history surface is now the queue table; keep this endpoint stable.
    from db.repositories.publish import get_publish_queue_history

    return {"publish_jobs": get_publish_queue_history(str(user.user_id))}
