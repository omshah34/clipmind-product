"""File: api/models/integration.py
Purpose: Pydantic models for integrations with external platforms (Zapier, Make, etc)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class IntegrationConfig(BaseModel):
    """Base configuration for integrations"""
    pass


class ZapierConfig(IntegrationConfig):
    """Zapier integration configuration"""
    zap_id: Optional[str] = Field(None, description="Zapier Zap ID (if managed)")
    webhook_url: Optional[str] = Field(None, description="Zapier webhook endpoint")


class MakeConfig(IntegrationConfig):
    """Make.com integration configuration"""
    scenario_id: Optional[str] = Field(None, description="Make scenario ID")
    webhook_url: str = Field(..., description="Make webhook endpoint")


class IntegrationCreateRequest(BaseModel):
    """Request to create a new integration"""
    integration_type: str = Field(..., description="Type: 'zapier' or 'make'")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name")
    trigger_events: list[str] = Field(..., min_items=1, description="Events that trigger this integration")
    config: dict = Field(default_factory=dict, description="Integration-specific config")


class IntegrationUpdateRequest(BaseModel):
    """Request to update an integration"""
    name: Optional[str] = Field(None, description="New name")
    trigger_events: Optional[list[str]] = Field(None, description="New trigger events")
    is_active: Optional[bool] = Field(None, description="Enable or disable")
    config: Optional[dict] = Field(None, description="Updated config")


class IntegrationResponse(BaseModel):
    """Response with integration details"""
    id: str = Field(..., description="Integration ID")
    integration_type: str = Field(..., description="Type: zapier, make, http, etc")
    name: str = Field(..., description="Human-readable name")
    trigger_events: list[str] = Field(..., description="Events that trigger this")
    is_active: bool = Field(..., description="Whether this integration is active")
    last_triggered_at: Optional[datetime] = Field(None, description="Last time it was triggered")
    created_at: datetime = Field(..., description="When created")
    updated_at: datetime = Field(..., description="Last update time")


class IntegrationListResponse(BaseModel):
    """Response listing all integrations for a user"""
    integrations: list[IntegrationResponse] = Field(..., description="List of integrations")
    total: int = Field(..., description="Total integrations")


class IntegrationTestRequest(BaseModel):
    """Request to test an integration"""
    event_type: str = Field("job.completed", description="Event type to test with")


class IntegrationTestResponse(BaseModel):
    """Response from integration test"""
    success: bool = Field(..., description="Whether the integration was triggered")
    status_code: Optional[int] = Field(None, description="HTTP status code")
    response_time_ms: int = Field(..., description="Response time in milliseconds")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    integration_type: str = Field(..., description="Which integration was tested")
