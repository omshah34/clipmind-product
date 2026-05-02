"""File: services/event_emitter.py
Purpose: Emit webhook events for job and clip completion.
         Provides clean API for triggering webhooks across the application.
"""

from __future__ import annotations

import logging
import hashlib
import json
from uuid import UUID
from datetime import datetime, timezone

from services.task_queue import is_redis_available

logger = logging.getLogger(__name__)
WEBHOOK_SCHEMA_VERSION = "2026-04-27"


def emit_event(event_type: str, event_data: dict, user_id: UUID | str) -> None:
    """Emit a webhook event to be delivered to all subscribing webhooks.
    
    This queues the webhook delivery as a Celery task for asynchronous processing.
    Also triggers any integrations (Zapier, Make) subscribed to this event.
    
    Args:
        event_type: Event type (e.g., "job.completed", "clips.generated")
        event_data: Event payload data to send
        user_id: User ID that triggered the event
    """
    logger.debug(f"[emit] Event: {event_type} for user {user_id}")

    # Gap 205: Generate deterministic idempotency key
    from core.utils import make_idempotency_key
    idempotency_key = make_idempotency_key(event_type, event_data)
    
    from workers.webhooks import deliver_webhook_event
    
    try:
        if not is_redis_available():
            deliver_webhook_event.run(
                event_type=event_type,
                event_data=event_data,
                user_id=str(user_id),
                idempotency_key=idempotency_key,
                snapshot={
                    "job_id": str(event_data.get("job_id", "")) if isinstance(event_data, dict) else None,
                    "event_type": event_type,
                    "status": event_data.get("status", "unknown") if isinstance(event_data, dict) else "unknown",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
            emit_to_integrations(event_type, event_data, user_id)
            return

        # Gap 246: Pass a snapshot of critical data to prevent race conditions
        # if the job is deleted before the worker fetches it.
        snapshot = {
            "job_id": None,
            "event_type": event_type,
            "status": "unknown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
        if isinstance(event_data, dict):
            snapshot["job_id"] = str(event_data.get("job_id", ""))
            snapshot["status"] = event_data.get("status", "unknown")

        # Queue webhook delivery as a Celery task
        deliver_webhook_event.delay(
            event_type=event_type,
            event_data=event_data,
            user_id=str(user_id),
            idempotency_key=idempotency_key,
            snapshot=snapshot,
        )
        
        # Also trigger integrations (Zapier, Make, etc)
        emit_to_integrations(event_type, event_data, user_id)
        
    except Exception as e:
        # Log but don't fail - webhook delivery should not block main flow
        logger.warning(f"[emit] Failed to queue event {event_type}: {e}")
        try:
            deliver_webhook_event.run(
                event_type=event_type,
                event_data=event_data,
                user_id=str(user_id),
                idempotency_key=idempotency_key,
                snapshot={
                    "job_id": str(event_data.get("job_id", "")) if isinstance(event_data, dict) else None,
                    "event_type": event_type,
                    "status": event_data.get("status", "unknown") if isinstance(event_data, dict) else "unknown",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as fallback_exc:
            logger.warning(f"[emit] Webhook fallback failed for {event_type}: {fallback_exc}")
        emit_to_integrations(event_type, event_data, user_id)


def emit_job_completed(
    job_id: UUID | str,
    user_id: UUID | str,
    status: str,
    clips_count: int,
    cost_usd: float,
) -> None:
    """Emit job.completed event."""
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
    """Emit clips.generated event."""
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
    """Emit clip.regenerated event."""
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
    """Emit campaign.created event."""
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
    """Emit campaign.updated event."""
    emit_event(
        event_type="campaign.updated",
        event_data={
            "campaign_id": str(campaign_id),
            "changes": changes,
        },
        user_id=user_id,
    )


def emit_to_integrations(event_type: str, event_data: dict, user_id: UUID | str) -> None:
    """Emit event to active integrations (Zapier, Make, etc)."""
    logger.debug(f"[integrations] Triggering for event: {event_type} user: {user_id}")

    if not is_redis_available():
        logger.warning(f"[integrations] Redis unavailable; falling back to synchronous delivery for {event_type}")
        try:
            from workers.integrations import process_integrations_for_event
            process_integrations_for_event(event_type, event_data, str(user_id))
        except Exception as exc:
            logger.warning(f"[integrations] Synchronous fallback failed for {event_type}: {exc}")
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
        logger.warning(f"[integrations] Failed to queue trigger for {event_type}: {e}")
        try:
            from workers.integrations import process_integrations_for_event
            process_integrations_for_event(event_type, event_data, str(user_id))
        except Exception as fallback_exc:
            logger.warning(f"[integrations] Synchronous fallback failed for {event_type}: {fallback_exc}")
