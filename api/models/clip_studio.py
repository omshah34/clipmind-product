"""File: api/models/clip_studio.py
Purpose: Pydantic models for Clip Studio (timeline editor, regeneration, preview).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ClipEdit(BaseModel):
    """User edit to a single clip's boundaries."""
    
    index: int = Field(description="Clip index in original list")
    original_start: float = Field(description="Original start time (seconds)")
    original_end: float = Field(description="Original end time (seconds)")
    user_start: Optional[float] = Field(default=None, description="User adjusted start")
    user_end: Optional[float] = Field(default=None, description="User adjusted end")
    regenerate_weights: Optional[dict[str, float]] = Field(default=None, description="Custom weights for this clip")


class RegenerationRequest(BaseModel):
    """Request to regenerate clips with custom parameters."""
    
    clip_count: int = Field(default=3, ge=1, le=10, description="Number of clips to find")
    custom_weights: Optional[dict[str, float]] = Field(default=None, description="Custom SCORE_WEIGHTS")
    instructions: Optional[str] = Field(default=None, description="Natural language instruction")


class RegenerationResult(BaseModel):
    """Result of a regeneration request."""
    
    regen_id: str = Field(description="Unique regeneration request ID")
    requested_at: datetime = Field(description="When request was made")
    completed_at: Optional[datetime] = Field(default=None, description="When regeneration completed")
    weights: dict[str, float] = Field(description="Weights used for this regeneration")
    instructions: Optional[str] = Field(description="Instructions used")
    clips: list[dict] = Field(description="Detected clips from regeneration")
    status: str = Field(default="pending", description="pending|completed|failed")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class TimelineData(BaseModel):
    """Full timeline state for a job."""
    
    clips: list[ClipEdit] = Field(description="User edits to clips")
    regeneration_results: list[RegenerationResult] = Field(default_factory=list, description="Past regenerations")


class AdjustClipBoundaryRequest(BaseModel):
    """Request to adjust a single clip's boundaries."""
    
    new_start: float = Field(description="New start time in seconds")
    new_end: float = Field(description="New end time in seconds")


class AdjustClipBoundaryResponse(BaseModel):
    """Response after adjusting clip boundaries."""
    
    clip_index: int
    new_start: float
    new_end: float
    duration: float
    clip_url: str = Field(description="URL of re-rendered clip")
    message: str


class ClipPreviewData(BaseModel):
    """Lightweight preview data for timeline UI (no FFmpeg render)."""
    
    job_id: str
    status: str = Field(description="Job status")
    transcript_words: list[dict] = Field(description="Transcript words with timestamps")
    current_clips: list[dict] = Field(description="Clip objects with all score fields")
    regeneration_count: int = Field(default=0, description="Number of regeneration requests queued")


class RegenerateClipsResponse(BaseModel):
    """Response when regeneration task is queued."""
    
    regen_id: str = Field(description="Unique ID for this regeneration")
    status: str = Field(default="queued", description="Task status")
    message: str
