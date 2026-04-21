"""File: api/models/social_publish.py
Purpose: Pydantic models for One-Click Publish (direct to TikTok, IG, YouTube)
"""

from pydantic import BaseModel, Field, HttpUrl
from uuid import UUID
from typing import Optional, List
from datetime import datetime


class SocialAccountRequest(BaseModel):
    """Request to connect social media account via OAuth."""
    platform: str = Field(description="tiktok, instagram, youtube")
    account_username: Optional[str] = None


class SocialAccountResponse(BaseModel):
    """Connected social media account."""
    account_id: UUID
    platform: str
    account_username: str
    account_id_platform: str
    is_connected: bool
    last_sync: Optional[datetime]
    scopes: List[str]
    created_at: datetime


class SocialAccountListResponse(BaseModel):
    """List of connected accounts."""
    accounts: List[SocialAccountResponse]
    total: int


class PublishRequest(BaseModel):
    """Request to publish a clip to social platforms."""
    job_id: UUID
    clip_index: int
    platforms: List[str] = Field(description="tiktok, instagram, youtube, linkedin")
    accounts: List[UUID] = Field(description="Account IDs to publish to")
    caption: str
    hashtags: Optional[List[str]] = None
    publish_immediately: bool = Field(default=False)
    scheduled_at: Optional[datetime] = None


class PlatformCaptionResponse(BaseModel):
    """AI-generated captions for each platform."""
    platform: str
    caption: str
    hashtags: List[str]
    character_count: int
    is_optimized: bool
    notes: Optional[str]


class CaptionOptimizationRequest(BaseModel):
    """Request AI to optimize captions for different platforms."""
    job_id: UUID
    clip_index: int
    base_caption: str
    target_platforms: List[str] = Field(description="tiktok, instagram, youtube")


class CaptionOptimizationResponse(BaseModel):
    """Optimized captions per platform."""
    job_id: UUID
    clip_index: int
    optimized_captions: List[PlatformCaptionResponse]


class PublishResponse(BaseModel):
    """Confirmation of publish request."""
    publish_id: UUID
    job_id: UUID
    clip_index: int
    platforms: List[str]
    accounts: List[UUID]
    status: str = Field(description="draft, queued, published, failed")
    platform_clip_ids: dict = Field(description="Map of platform -> clip ID")
    published_urls: Optional[dict] = None
    estimated_reach: Optional[int] = None
    created_at: datetime


class PublishStatusResponse(BaseModel):
    """Status of a published clip."""
    publish_id: UUID
    platform: str
    status: str  # draft, queued, published, failed
    platform_clip_id: Optional[str]
    url: Optional[HttpUrl]
    error_message: Optional[str]
    published_at: Optional[datetime]
    views: Optional[int]
    likes: Optional[int]


class SmartScheduleRequest(BaseModel):
    """Request smart scheduling based on audience timezone."""
    job_id: UUID
    clip_indices: List[int]
    platforms: List[str]
    audience_timezone: str = Field(description="e.g., America/New_York")


class SmartScheduleResponse(BaseModel):
    """Recommended publishing times."""
    recommendations: List[dict] = Field(
        description="Suggested times with predicted engagement"
    )
    best_time: datetime
    predicted_peak_engagement: float
    reasoning: str
