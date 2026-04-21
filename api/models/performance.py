"""File: api/models/performance.py
Purpose: Pydantic models for clip performance tracking and analytics.

Models:
  - PerformanceCreateRequest: Submit performance metrics for a clip
  - PerformanceUpdateRequest: Update performance metrics
  - PerformanceResponse: Return clip performance data
  - PerformanceListResponse: Paginated list of clips
  - PerformanceSummary: Aggregated stats across clips
  - PerformanceAlert: Performance anomaly or milestone alert
  - PlatformAccount: Connected social media account
"""

from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class PerformanceCreateRequest(BaseModel):
    """Request to submit performance metrics for a clip."""
    job_id: UUID
    clip_index: int = Field(..., ge=0, description="0-based clip index")
    platform: str = Field(..., min_length=1, max_length=50, description="TikTok, Instagram, YouTube, etc")
    platform_clip_id: Optional[str] = Field(None, max_length=255, description="Platform-specific clip ID")
    views: int = Field(default=0, ge=0)
    likes: int = Field(default=0, ge=0)
    saves: int = Field(default=0, ge=0)
    shares: int = Field(default=0, ge=0)
    comments: int = Field(default=0, ge=0)
    source_type: str = Field(default="real", description="mock or real")
    ai_predicted_score: Optional[float] = None
    average_watch_time_seconds: Optional[float] = Field(None, ge=0)
    completion_rate: Optional[float] = Field(None, ge=0, le=1, description="0-1 scale")
    published_date: Optional[datetime] = None


class PerformanceUpdateRequest(BaseModel):
    """Request to update performance metrics for a clip."""
    views: Optional[int] = Field(None, ge=0)
    likes: Optional[int] = Field(None, ge=0)
    saves: Optional[int] = Field(None, ge=0)
    shares: Optional[int] = Field(None, ge=0)
    comments: Optional[int] = Field(None, ge=0)
    average_watch_time_seconds: Optional[float] = Field(None, ge=0)
    completion_rate: Optional[float] = Field(None, ge=0, le=1)


class PerformanceResponse(BaseModel):
    """Performance metrics for a single clip on a platform."""
    id: UUID
    job_id: UUID
    clip_index: int
    platform: str
    platform_clip_id: Optional[str] = None
    views: int
    likes: int
    saves: int
    shares: int
    comments: int
    source_type: str
    ai_predicted_score: Optional[float] = None
    performance_delta: float = 0.0
    milestone_tier: Optional[str] = None
    window_complete: bool = False
    engagement_score: float = Field(description="Calculated engagement ratio")
    save_rate: float = Field(description="Saves / Views")
    share_rate: float = Field(description="Shares / Views")
    comment_rate: float = Field(description="Comments / Views")
    average_watch_time_seconds: Optional[float] = None
    completion_rate: Optional[float] = None
    published_date: Optional[datetime] = None
    synced_at: datetime = Field(description="When metrics were last synced")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class PerformanceListResponse(BaseModel):
    """Paginated list of performance records."""
    performances: List[PerformanceResponse]
    total: int
    limit: int
    offset: int


class PerformancePlatformStats(BaseModel):
    """Aggregated stats for clips on a specific platform."""
    platform: str
    total_clips: int
    total_views: int
    total_likes: int
    total_saves: int
    total_shares: int
    total_comments: int
    average_engagement_score: float
    average_completion_rate: Optional[float]
    best_performing_clip_index: Optional[int] = Field(None, description="Clip index with highest engagement")
    worst_performing_clip_index: Optional[int] = Field(None, description="Clip index with lowest engagement")


class PerformanceSummary(BaseModel):
    """Aggregated performance summary across all clips."""
    job_id: UUID
    total_clips: int
    platforms: List[str] = Field(description="Platforms with performance data")
    total_views: int
    total_likes: int
    total_saves: int
    total_shares: int
    total_comments: int
    overall_engagement_score: float = Field(description="Average engagement across all clips")
    average_completion_rate: Optional[float] = Field(None, description="Average view completion rate")
    platform_stats: List[PerformancePlatformStats] = Field(description="Per-platform breakdown")
    top_platform: str = Field(description="Platform with most engagement")
    best_clip_index: int = Field(description="Clip index with best performance")
    worst_clip_index: int = Field(description="Clip index with worst performance")
    synced_at: datetime = Field(description="When data was last synced")


class PerformanceAlertResponse(BaseModel):
    """Alert for performance anomaly or milestone."""
    id: UUID
    clip_perf_id: UUID
    alert_type: str = Field(description="milestone, anomaly, trending")
    message: str
    metric_name: Optional[str] = Field(None, description="views, engagement_score, completion_rate")
    metric_value: Optional[float] = None
    threshold: Optional[float] = None
    is_read: bool = False
    created_at: datetime
    
    class Config:
        from_attributes = True


class PerformanceAlertListResponse(BaseModel):
    """List of performance alerts."""
    alerts: List[PerformanceAlertResponse]
    total: int
    unread_count: int


class PlatformAccountResponse(BaseModel):
    """Connected social media account."""
    id: UUID
    platform: str = Field(description="TikTok, Instagram, YouTube, etc")
    account_id: str = Field(description="Platform account ID")
    account_name: str = Field(description="Platform username/handle")
    scopes: List[str] = Field(description="Granted permissions")
    synced_at: Optional[datetime] = Field(None, description="When metrics were last synced")
    created_at: datetime
    
    class Config:
        from_attributes = True


class PlatformAccountListResponse(BaseModel):
    """List of connected platform accounts."""
    accounts: List[PlatformAccountResponse]
    total: int


class PerformanceTimeSeriesPoint(BaseModel):
    """Single data point for time series chart."""
    timestamp: datetime
    views: int
    likes: int
    saves: int
    engagement_score: float


class PerformanceTimeSeriesResponse(BaseModel):
    """Time series data for a clip on a platform."""
    job_id: UUID
    clip_index: int
    platform: str
    data_points: List[PerformanceTimeSeriesPoint]
    earliest_date: datetime
    latest_date: datetime
