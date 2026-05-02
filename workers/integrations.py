"""Workers for triggering integrations (Zapier, Make, etc).

This module handles async queuing and delivery of events to external integrations.
Each integration can subscribe to specific event types and receive formatted payloads.

Integration types supported:
- zapier: Webhook connector on Zapier (formatted with top-level fields)
- make: Make.com/Integromat (formatted with metadata + payload structure)
- slack: Slack webhooks (formatted as message blocks)

Event types:
- job.completed: Job processing completed
- clips.generated: Clips generated from job
- clip.regenerated: Clip regenerated in studio
- campaign.created: Campaign created
- campaign.updated: Campaign updated
"""

import logging
from uuid import UUID
from services.integration_adapters import get_adapter
from db.repositories import integrations as queries
from workers.celery_app import celery_app as app
import requests
from typing import Optional

logger = logging.getLogger(__name__)


def process_integrations_for_event(
    event_type: str,
    event_data: dict,
    user_id: str,
) -> None:
    """Get all active integrations for an event type and trigger them.
    
    This task fetches integrations subscribed to the event and calls trigger_integration_task
    for each one to send the formatted event asynchronously.
    
    Args:
        event_type: Event type (e.g., "job.completed")
        event_data: Raw event data dict
        user_id: User ID that triggered the event
    """
    logger.debug(f"[integrations] Triggering for {event_type} on behalf of {user_id}")
    
    try:
        # Get all integrations subscribed to this event type
        integrations = queries.list_active_integrations_for_event(
            event_type=event_type,
            user_id=user_id,
        )
        
        logger.debug(f"[integrations] Found {len(integrations)} integrations for {event_type}")
        
        # Queue trigger task for each integration
        for integration in integrations:
            trigger_integration_task.delay(
                integration_id=str(integration['id']),
                event_type=event_type,
                event_data=event_data,
                user_id=user_id,
            )
    
    except Exception as e:
        logger.error(f"[integrations] Error querying integrations: {e}")
        # Don't retry - this is a query issue, not a delivery issue


@app.task(bind=True, max_retries=0)
def trigger_integrations_for_event(
    self,
    event_type: str,
    event_data: dict,
    user_id: str,
) -> None:
    process_integrations_for_event(event_type, event_data, user_id)


@app.task(bind=True, max_retries=0)
def trigger_integration_task(
    self,
    integration_id: str,
    event_type: str,
    event_data: dict,
    user_id: str,
) -> None:
    """Trigger a single integration with a formatted event.
    
    This task formats the event using the appropriate adapter (Zapier, Make, etc),
    sends it to the integration's webhook URL, and logs the result.
    
    Args:
        integration_id: Integration ID
        event_type: Event type
        event_data: Raw event data
        user_id: User ID
    """
    logger.debug(
        f"[integrations] Triggering integration {integration_id} for {event_type}"
    )
    
    try:
        # Fetch integration config
        integration = queries.get_integration(integration_id)
        if not integration:
            logger.error(f"[integrations] Integration {integration_id} not found")
            return
        
        # Get the appropriate adapter for this integration type
        adapter = get_adapter(integration['type'])
        
        # Format the event using the adapter
        formatted_event = adapter.format_event(event_type, event_data)
        
        logger.debug(
            f"[integrations] Formatted event for {integration['type']}: "
            f"{event_type} -> {formatted_event}"
        )
        
        # Send to the integration webhook URL
        await_integration_delivery(
            integration_id=integration_id,
            config=integration['config'],
            formatted_event=formatted_event,
            event_type=event_type,
        )
        
        # Update last_triggered_at timestamp
        queries.update_integration_last_triggered(integration_id)
        
        logger.info(
            f"[integrations] Successfully triggered {integration['type']} "
            f"integration {integration_id} for {event_type}"
        )
    
    except Exception as e:
        logger.error(
            f"[integrations] Error triggering integration {integration_id}: {e}",
            exc_info=True,
        )


def await_integration_delivery(
    integration_id: str,
    config: dict,
    formatted_event: dict,
    event_type: str,
) -> None:
    """Send formatted event to the integration webhook URL.
    
    Args:
        integration_id: Integration ID (for logging)
        config: Integration config dict (contains webhook_url)
        formatted_event: Formatted event payload
        event_type: Event type (for logging)
    
    Raises:
        Exception: If delivery fails
    """
    webhook_url = config.get('webhook_url')
    if not webhook_url:
        logger.error(
            f"[integrations] Integration {integration_id} missing webhook_url in config"
        )
        return
    
    timeout_seconds = config.get('timeout_seconds', 30)
    
    logger.debug(
        f"[integrations] Sending {event_type} to {webhook_url} "
        f"(timeout={timeout_seconds}s)"
    )
    
    try:
        # Send POST request to integration webhook
        response = requests.post(
            webhook_url,
            json=formatted_event,
            timeout=timeout_seconds,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'ClipMind-Integration/1.0',
            },
        )
        
        # Log response status
        if response.status_code >= 400:
            logger.warning(
                f"[integrations] Integration returned {response.status_code}: "
                f"{response.text[:200]}"
            )
        else:
            logger.debug(
                f"[integrations] Integration returned {response.status_code}"
            )
    
    except requests.Timeout:
        logger.error(
            f"[integrations] Timeout sending to {webhook_url} "
            f"(timeout={timeout_seconds}s)"
        )
        raise
    
    except requests.ConnectionError as e:
        logger.error(
            f"[integrations] Connection error sending to {webhook_url}: {e}"
        )
        raise
    
    except Exception as e:
        logger.error(
            f"[integrations] Error sending to {webhook_url}: {e}",
            exc_info=True,
        )
        raise
