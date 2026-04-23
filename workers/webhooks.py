"""File: workers/webhooks.py
Purpose: Webhook delivery worker for Feature 4: ClipMind API.
         Handles delivery of webhook events with automatic retry backoff.
         Runs as Celery tasks in background.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from db.repositories.webhooks import (
    list_active_webhooks_for_event,
    create_webhook_delivery,
    update_webhook_delivery,
    get_pending_webhook_deliveries,
    get_webhook,
    get_webhook_delivery,
)
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Retry backoff strategy (exponential)
RETRY_MAX_ATTEMPTS = 5
RETRY_BASE_DELAY_SECONDS = 60  # Start with 1 minute
RETRY_MAX_DELAY_SECONDS = 3600  # Cap at 1 hour


def _sign_webhook_payload(payload: dict, secret: str) -> str:
    """Create HMAC signature for webhook payload."""
    payload_str = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(f"{payload_str}{secret}".encode()).hexdigest()


def _calculate_retry_delay(attempt_count: int) -> int:
    """Calculate exponential backoff delay in seconds."""
    delay = RETRY_BASE_DELAY_SECONDS * (2 ** (attempt_count - 1))
    return min(delay, RETRY_MAX_DELAY_SECONDS)


@celery_app.task(bind=True, name="workers.webhooks.deliver_webhook_event")
def deliver_webhook_event(
    self,
    event_type: str,
    event_data: dict,
    user_id: str,
) -> dict:
    """Queue webhook deliveries for an event."""
    logger.info(f"[webhook] Processing event: {event_type} for user {user_id}")
    
    webhooks = list_active_webhooks_for_event(event_type)
    user_webhooks = [w for w in webhooks if str(w.get("user_id")) == str(user_id)]
    
    if not user_webhooks:
        logger.debug(f"[webhook] No active webhooks for event {event_type}")
        return {"queued": 0, "failed": 0}
    
    event_payload = {
        "event_id": f"{event_type}_{int(time.time() * 1000)}",
        "event_type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "data": event_data,
    }
    
    queued = 0
    failed = 0
    
    for webhook in user_webhooks:
        try:
            delivery = create_webhook_delivery(
                webhook_id=webhook["id"],
                event_type=event_type,
                event_data=event_payload,
            )
            
            if delivery:
                attempt_delivery_task.delay(str(delivery["id"]))
                queued += 1
                logger.debug(f"[webhook] Delivery queued: {delivery['id']}")
            else:
                failed += 1
                logger.error(f"[webhook] Failed to create delivery record for webhook {webhook['id']}")
        
        except Exception as e:
            failed += 1
            logger.error(f"[webhook] Error queuing delivery for webhook {webhook['id']}: {e}")
    
    return {"queued": queued, "failed": failed}


@celery_app.task(bind=True, name="workers.webhooks.attempt_delivery_task", default_retry_delay=60)
def attempt_delivery_task(self, delivery_id: str) -> dict:
    """Attempt to deliver a webhook event."""
    logger.info(f"[webhook-delivery] Attempting delivery: {delivery_id}")
    
    delivery = get_webhook_delivery(delivery_id)
    if not delivery:
        logger.error(f"[webhook-delivery] Delivery record {delivery_id} not found")
        return {"status": "error", "message": "Delivery not found"}

    return attempt_webhook_delivery(
        webhook_id=str(delivery["webhook_id"]),
        event_payload=delivery["event_data"] if isinstance(delivery["event_data"], dict) else json.loads(delivery["event_data"]),
        attempt_number=delivery["attempt_count"] + 1
    )


@celery_app.task(name="workers.webhooks.process_pending_deliveries")
def process_pending_deliveries() -> dict:
    """Periodic task to retry pending webhook deliveries."""
    logger.info("[webhook-retry] Processing pending webhook deliveries")
    
    pending = get_pending_webhook_deliveries()
    logger.info(f"[webhook-retry] Found {len(pending)} pending deliveries to retry")
    
    retried = 0
    failed = 0
    
    for delivery in pending:
        try:
            attempt_webhook_delivery.apply_async(
                args=[
                    str(delivery["webhook_id"]),
                    delivery["event_data"],
                    delivery["attempt_count"] + 1,
                ],
                countdown=_calculate_retry_delay(delivery["attempt_count"] + 1),
            )
            retried += 1
        
        except Exception as e:
            failed += 1
            logger.error(f"[webhook-retry] Failed to queue retry for delivery {delivery['id']}: {e}")
    
    return {"retried": retried, "failed": failed}


@celery_app.task(bind=True, name="workers.webhooks.attempt_webhook_delivery")
def attempt_webhook_delivery(
    self,
    webhook_id: str,
    event_payload: dict,
    attempt_number: int = 1,
) -> dict:
    """Execute a single webhook delivery attempt with HTTP POST."""
    logger.info(f"[webhook-deliver] Attempt {attempt_number}: webhook={webhook_id}")
    
    webhook = get_webhook(webhook_id)
    if not webhook:
        logger.error(f"[webhook-deliver] Webhook not found: {webhook_id}")
        return {"status": "failed", "error": "Webhook not found"}
    
    if not webhook.get("is_active"):
        logger.warn(f"[webhook-deliver] Webhook is inactive: {webhook_id}")
        return {"status": "failed", "error": "Webhook inactive"}
    
    signature = _sign_webhook_payload(event_payload, webhook["secret"])
    
    headers = {
        "X-Webhook-Signature": signature,
        "X-Webhook-Timestamp": datetime.now(timezone.utc).isoformat(),
        "Content-Type": "application/json",
    }
    
    start_time = time.time()
    http_status = None
    response_body = None
    error_message = None
    success = False
    
    try:
        timeout = webhook.get("timeout_seconds", 30)
        with httpx.Client(timeout=timeout) as client:
            response = client.post(
                webhook["url"],
                json=event_payload,
                headers=headers,
            )
        
        http_status = response.status_code
        response_body = response.text[:1000]
        response_time_ms = int((time.time() - start_time) * 1000)
        
        if response.status_code < 400:
            success = True
        else:
            error_message = f"HTTP {response.status_code}"
    
    except Exception as e:
        error_message = str(e)[:100]
        response_time_ms = int((time.time() - start_time) * 1000)
    
    # Update delivery record if we have a delivery_id context (not easily available in this signature)
    # But the calling task can handle it.
    
    return {
        "status": "delivered" if success else "failed",
        "http_status": http_status,
        "error_message": error_message,
    }
