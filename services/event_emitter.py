"""File: services/event_emitter.py
Purpose: Emit webhook events for job and clip completion.
         Provides clean API for triggering webhooks across the application.
"""

from __future__ import annotations

import logging
from uuid import UUID

from services.task_queue import is_redis_available

logger = logging.getLogger(__name__)


def emit_event(event_type: str, event_data: dict, user_id: UUID | str) -> None:
    """Emit a webhook event to be delivered to all subscribing webhooks.
    
    This queues the webhook delivery as a Celery task for asynchronous processing.
    Also triggers any integrations (Zapier, Make) subscribed to this event.
    
    Args:
        event_type: Event type (e.g., "job.completed", "clips.generated")
        event_data: Event payload data to send
        user_id: User ID that triggered the event
    
    Supported events:
        - job.completed: Job processing completed (success or failure)
        - clips.generated: Clips were generated from a job
        - clip.regenerated: Clip was regenerated in Clip Studio
        - campaign.created: Campaign was created
        - campaign.updated: Campaign was updated
    """
    logger.debug(f"[emit] Event: {event_type} for user {user_id}")

    if not is_redis_available():
        logger.warning(f"[emit] Redis unavailable; skipping event {event_type}")
        return

    from workers.webhooks import deliver_webhook_event
    
    try:
        # Queue webhook delivery as a Celery task
        deliver_webhook_event.delay(
            event_type=event_type,
            event_data=event_data,
            user_id=str(user_id),
        )
        
        # Also trigger integrations (Zapier, Make, etc)
        emit_to_integrations(event_type, event_data, user_id)
    
    except Exception as e:
        # Log but don't fail - webhook delivery should not block main flow
        logger.warning(f"[emit] Failed to queue event {event_type}: {e}")


def emit_job_completed(
    job_id: UUID | str,
    user_id: UUID | str,
    status: str,
    clips_count: int,
    cost_usd: float,
) -> None:
    """Emit job.completed event.
    
    Args:
        job_id: Job ID that completed
        user_id: User ID
        status: Final status ("completed" or "failed")
        clips_count: Number of clips generated
        cost_usd: Cost of processing
    """
    emit_event(
        event_type="job.completed",
        event_data={
            "job_id": str(job_id),
            "status": status,
            "clips_count": clips_count,
            "estimated_cost_usd": cost_usd,
        },
        user_id=user_id,
    )


def emit_clips_generated(
    job_id: UUID | str,
    user_id: UUID | str,
    clips: list[dict],
) -> None:
    """Emit clips.generated event.
    
    Args:
        job_id: Job ID
        user_id: User ID
        clips: List of generated clips
    """
    emit_event(
        event_type="clips.generated",
        event_data={
            "job_id": str(job_id),
            "clips_count": len(clips),
            "clips": clips[:3],  # Send top 3 clips in event
        },
        user_id=user_id,
    )


def emit_clip_regenerated(
    job_id: UUID | str,
    user_id: UUID | str,
    clip_index: int,
    regen_id: UUID | str,
) -> None:
    """Emit clip.regenerated event.
    
    Args:
        job_id: Job ID
        user_id: User ID
        clip_index: Index of regenerated clip
        regen_id: Regeneration request ID
    """
    emit_event(
        event_type="clip.regenerated",
        event_data={
            "job_id": str(job_id),
            "clip_index": clip_index,
            "regen_id": str(regen_id),
        },
        user_id=user_id,
    )


def emit_campaign_created(
    campaign_id: UUID | str,
    user_id: UUID | str,
    campaign_name: str,
) -> None:
    """Emit campaign.created event.
    
    Args:
        campaign_id: Campaign ID
        user_id: User ID
        campaign_name: Campaign name
    """
    emit_event(
        event_type="campaign.created",
        event_data={
            "campaign_id": str(campaign_id),
            "campaign_name": campaign_name,
        },
        user_id=user_id,
    )


def emit_campaign_updated(
    campaign_id: UUID | str,
    user_id: UUID | str,
    changes: dict,
) -> None:
    """Emit campaign.updated event.
    
    Args:
        campaign_id: Campaign ID
        user_id: User ID
        changes: Dict of changed fields
    """
    emit_event(
        event_type="campaign.updated",
        event_data={
            "campaign_id": str(campaign_id),
            "changes": changes,
        },
        user_id=user_id,
    )


def emit_to_integrations(event_type: str, event_data: dict, user_id: UUID | str) -> None:
    """Emit event to active integrations (Zapier, Make, etc).
    
    This triggers Celery tasks to send formatted event data to integration endpoints.
    Integrations are triggered asynchronously and failures don't block the main flow.
    
    Args:
        event_type: Event type (e.g., "job.completed")
        event_data: Raw event data
        user_id: User ID that triggered the event
    """
    logger.debug(f"[integrations] Triggering for event: {event_type} user: {user_id}")

    if not is_redis_available():
        logger.warning(f"[integrations] Redis unavailable; skipping event {event_type}")
        return

    from workers.integrations import trigger_integrations_for_event
    
    try:
        # Queue integration triggers as a Celery task
        trigger_integrations_for_event.delay(
            event_type=event_type,
            event_data=event_data,
            user_id=str(user_id),
        )
    
    except Exception as e:
        # Log but don't fail - integration triggers should not block main flow
        logger.warning(f"[integrations] Failed to queue trigger for {event_type}: {e}")
