"""File: api/models/campaign.py
Purpose: Pydantic models for Clip Campaigns feature.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleConfig(BaseModel):
    """Campaign scheduling configuration."""
    
    publish_interval_days: int = Field(default=1, ge=1, le=30, description="Days between clip publications")
    publish_hour: int = Field(default=9, ge=0, le=23, description="Hour of day to publish (24-hour format)")
    publish_timezone: str = Field(default="UTC", description="Timezone for scheduling (e.g., US/Eastern)")
    publish_to_channels: list[str] = Field(default_factory=lambda: ["tiktok", "instagram"], description="Target platforms")
    hashtags: list[str] = Field(default_factory=list, description="Auto-append hashtags to captions")
    caption_template: Optional[str] = Field(default=None, description="Template for auto-generated captions")
    enabled: bool = Field(default=True, description="Whether scheduling is active")


class CampaignCreate(BaseModel):
    """Request to create a new campaign."""
    
    name: str = Field(min_length=1, max_length=255, description="Campaign name")
    description: Optional[str] = Field(default=None, description="Campaign description")
    schedule_config: Optional[ScheduleConfig] = Field(default_factory=ScheduleConfig, description="Scheduling rules")


class CampaignUpdate(BaseModel):
    """Request to update a campaign."""
    
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = Field(default=None)
    schedule_config: Optional[ScheduleConfig] = Field(default=None)
    status: Optional[str] = Field(default=None, description="active|paused|archived")


class CampaignRecord(BaseModel):
    """Full campaign database record."""
    
    id: UUID
    user_id: UUID
    name: str
    description: Optional[str]
    schedule_config: dict
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class CampaignResponse(BaseModel):
    """Single campaign response."""
    
    id: UUID
    name: str
    description: Optional[str]
    status: str
    clip_count: int = Field(default=0, description="Number of clips in campaign")
    schedule_config: ScheduleConfig
    created_at: datetime
    updated_at: datetime


class CampaignListResponse(BaseModel):
    """Paginated campaign list response."""
    
    campaigns: list[CampaignResponse]
    total: int
    limit: int
    offset: int


class BatchUploadRequest(BaseModel):
    """Request to batch upload multiple videos to a campaign."""
    
    campaign_id: UUID
    # Note: Files are multipart/form-data, not JSON
    # Frontend will handle FormData construction


class ClipForPublishing(BaseModel):
    """Clip scheduled for future publishing."""
    
    job_id: UUID
    campaign_id: UUID
    clip_index: int
    start_time: float
    end_time: float
    duration: float
    final_score: float
    scheduled_publish_date: datetime
    reason: str


class CampaignCalendarResponse(BaseModel):
    """Campaign calendar with scheduled clips."""
    
    campaign_id: UUID
    clips_by_date: dict[str, list[ClipForPublishing]] = Field(description="Clips grouped by publish date (YYYY-MM-DD)")
    total_scheduled_clips: int
    date_range_start: datetime
    date_range_end: datetime


class CampaignStatsResponse(BaseModel):
    """Statistics for a campaign."""
    
    campaign_id: UUID
    total_videos_uploaded: int
    total_clips_detected: int
    clips_scheduled: int
    clips_published: int
    next_publish_date: Optional[datetime]
    avg_clip_score: float = Field(description="Average final_score across all clips")
