"""File: api/models/webhook.py
Purpose: Pydantic models for webhooks (Feature 4: ClipMind API)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, HttpUrl


class WebhookEventType(BaseModel):
    """Supported webhook event types"""
    job_completed = "job.completed"
    clips_generated = "clips.generated"
    clip_regenerated = "clip.regenerated"
    campaign_created = "campaign.created"
    campaign_updated = "campaign.updated"


class WebhookCreateRequest(BaseModel):
    """Request to create a new webhook"""
    url: str = Field(..., description="Endpoint URL where webhooks will be sent (must be HTTPS)")
    event_types: list[str] = Field(..., min_items=1, description="Events to subscribe to: job.completed, clips.generated, clip.regenerated, campaign.created, campaign.updated")
    timeout_seconds: int = Field(30, ge=5, le=300, description="HTTP timeout in seconds")


class WebhookUpdateRequest(BaseModel):
    """Request to update a webhook"""
    url: Optional[str] = Field(None, description="New endpoint URL")
    event_types: Optional[list[str]] = Field(None, description="New list of events to subscribe to")
    is_active: Optional[bool] = Field(None, description="Enable or disable this webhook")
    timeout_seconds: Optional[int] = Field(None, ge=5, le=300, description="New HTTP timeout in seconds")


class WebhookResponse(BaseModel):
    """Response with webhook details"""
    id: str = Field(..., description="Webhook ID")
    url: str = Field(..., description="Endpoint URL")
    event_types: list[str] = Field(..., description="Subscribed events")
    is_active: bool = Field(..., description="Whether this webhook is active")
    timeout_seconds: int = Field(..., description="HTTP timeout in seconds")
    retry_max: int = Field(..., description="Max retry attempts for failed deliveries")
    created_at: datetime = Field(..., description="When this webhook was created")
    updated_at: datetime = Field(..., description="Last update time")


class WebhookListResponse(BaseModel):
    """Response listing all webhooks for a user"""
    webhooks: list[WebhookResponse] = Field(..., description="List of webhooks")
    total: int = Field(..., description="Total number of webhooks")


class WebhookTestRequest(BaseModel):
    """Request to test a webhook with sample event"""
    event_type: str = Field("job.completed", description="Event type to test with")


class WebhookTestResponse(BaseModel):
    """Response from webhook test"""
    success: bool = Field(..., description="Whether the webhook was successfully delivered")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class WebhookEventPayload(BaseModel):
    """Generic webhook event payload structure"""
    event_id: str = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Type of event: job.completed, clips.generated, etc")
    schema_version: str = Field(default="2026-04-27", description="Webhook payload schema version")
    timestamp: datetime = Field(..., description="When this event occurred")
    user_id: str = Field(..., description="User ID who triggered this event")
    data: dict = Field(..., description="Event-specific data")


class JobCompletedEvent(WebhookEventPayload):
    """Payload for job.completed event"""
    data: dict = Field(..., description="Contains: job_id, status, clips_count, clip_scores, estimated_cost_usd")


class ClipsGeneratedEvent(WebhookEventPayload):
    """Payload for clips.generated event"""
    data: dict = Field(..., description="Contains: job_id, clips (array of clip data)")


class WebhookDeliveryLogResponse(BaseModel):
    """Delivery log entry for webhook attempts"""
    id: str = Field(..., description="Delivery attempt ID")
    webhook_id: str = Field(..., description="Webhook ID")
    event_type: str = Field(..., description="Event type that was delivered")
    status: str = Field(..., description="Status: pending, delivered, failed, dropped")
    attempt_count: int = Field(..., description="How many times this was retried")
    http_status: Optional[int] = Field(None, description="HTTP status code received")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    created_at: datetime = Field(..., description="When delivery was first attempted")
    delivered_at: Optional[datetime] = Field(None, description="When it was successfully delivered")
    next_retry_at: Optional[datetime] = Field(None, description="When it will be retried next")


class WebhookLogsResponse(BaseModel):
    """Response listing delivery logs for a webhook"""
    webhook_id: str = Field(..., description="Webhook ID")
    deliveries: list[WebhookDeliveryLogResponse] = Field(..., description="Delivery log entries")
    total: int = Field(..., description="Total deliveries logged")
    failed_count: int = Field(..., description="Number of failed deliveries")
    pending_count: int = Field(..., description="Number of pending deliveries awaiting retry")
