"""File: api/routes/webhooks.py
Purpose: Secure webhook receiver endpoints with signature verification.
         Handles Stripe payments and YouTube PubSubHubbub notifications.
"""
from __future__ import annotations

import hmac
import hashlib
import logging
from typing import Any

from fastapi import APIRouter, Request, Header, HTTPException, status
import stripe

from core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request, 
    stripe_signature: str = Header(None)
) -> dict[str, Any]:
    """Handle incoming Stripe events with signature verification."""
    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET is not configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Webhook secret not configured."
        )

    payload = await request.body()
    
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except ValueError:
        # Invalid payload
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        # Invalid signature
        logger.warning("Invalid Stripe signature detected.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid signature")

    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        job_id = session.get('metadata', {}).get('job_id')
        if job_id:
            from db.repositories.jobs import get_job
            if not get_job(job_id):
                logger.error(f"Stripe webhook: Job {job_id} not found in DB.")
                raise HTTPException(status_code=404, detail="Job not found")
        
        # TODO: Trigger credits top-up or subscription activation
        logger.info(f"Payment successful for session {session.id}")
        if job_id:
            logger.info(f"Fulfilling order for job_id: {job_id}")
    
    return {"status": "success"}


@router.get("/youtube")
async def youtube_verify(
    request: Request,
    hub_mode: str = "",
    hub_challenge: str = "",
    hub_topic: str = ""
) -> str:
    """Handle YouTube PubSubHubbub verification challenge."""
    # hub.mode=subscribe or hub.mode=unsubscribe
    # hub.challenge=...
    # hub.topic=...
    expected_topic = "https://www.youtube.com/xml/feeds/videos.xml?channel_id="
    if hub_mode == "subscribe" and expected_topic not in hub_topic:
        logger.warning(f"YouTube verification failed: Topic mismatch. Got {hub_topic}")
        raise HTTPException(status_code=400, detail="Invalid topic")

    logger.info(f"YouTube verification challenge: mode={hub_mode}, topic={hub_topic}")
    return hub_challenge


@router.post("/youtube")
async def youtube_webhook(
    request: Request,
    x_hub_signature: str = Header(None)
) -> dict[str, Any]:
    """Handle YouTube PubSubHubbub notifications with HMAC verification."""
    payload = await request.body()

    if settings.youtube_webhook_secret:
        if not x_hub_signature:
            logger.warning("Missing X-Hub-Signature for YouTube webhook.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
        
        # YouTube uses sha1 in X-Hub-Signature=sha1=HASH
        sha_name, signature = x_hub_signature.split('=')
        if sha_name != 'sha1':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only sha1 supported")

        mac = hmac.new(settings.youtube_webhook_secret.encode(), payload, hashlib.sha1)
        if not hmac.compare_digest(mac.hexdigest(), signature):
            logger.warning("Invalid YouTube signature detected.")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")

    # Process XML payload (Atom feed)
    # TODO: Parse XML to detect new video upload and trigger Autopilot
    logger.info("YouTube notification received.")
    
    return {"status": "received"}
