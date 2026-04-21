"""File: api/models/api_key.py
Purpose: Pydantic models for API key management (Feature 4: ClipMind API)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ApiKeyCreateRequest(BaseModel):
    """Request to create a new API key"""
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable name for this key")
    expires_in_days: Optional[int] = Field(None, ge=1, le=365, description="Days until key expires (optional)")


class ApiKeyResponse(BaseModel):
    """API key response (shown once after creation, contains full key)"""
    id: str = Field(..., description="Key ID")
    key: str = Field(..., description="FULL API key (shown only once at creation)")
    name: str = Field(..., description="Human-readable name")
    key_prefix: str = Field(..., description="Key prefix for identification (e.g., 'clipmind_abc...')")
    is_active: bool = Field(..., description="Whether this key is active")
    rate_limit_per_min: int = Field(..., description="Rate limit: requests per minute")
    created_at: datetime = Field(..., description="When this key was created")
    expires_at: Optional[datetime] = Field(None, description="When this key expires (if set)")


class ApiKeyListItem(BaseModel):
    """API key info for listing (no full key revealed)"""
    id: str = Field(..., description="Key ID")
    name: str = Field(..., description="Human-readable name")
    key_prefix: str = Field(..., description="Key prefix (e.g., 'clipmind_abc...')")
    is_active: bool = Field(..., description="Whether this key is active")
    rate_limit_per_min: int = Field(..., description="Rate limit: requests per minute")
    last_used_at: Optional[datetime] = Field(None, description="Last time this key was used")
    created_at: datetime = Field(..., description="When this key was created")
    expires_at: Optional[datetime] = Field(None, description="When this key expires (if set)")


class ApiKeyListResponse(BaseModel):
    """Response listing all API keys for a user"""
    keys: list[ApiKeyListItem] = Field(..., description="List of API keys")
    total: int = Field(..., description="Total number of keys")


class ApiKeyRotateRequest(BaseModel):
    """Request to rotate (invalidate) an API key"""
    keep_access: bool = Field(False, description="If true, generate new key before revoking old one")


class ApiKeyRotateResponse(BaseModel):
    """Response after rotating an API key"""
    old_key_id: str = Field(..., description="ID of the invalidated key")
    new_key: Optional[str] = Field(None, description="New key if keep_access=true")
    new_key_id: Optional[str] = Field(None, description="New key ID if keep_access=true")
    message: str = Field(..., description="Status message")
