"""File: api/models/clip_sequences.py
Purpose: Pydantic models for Clip Sequences (multi-clip narrative arcs)
"""

from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional
from datetime import datetime


class ClipSequenceRequest(BaseModel):
    """Request to analyze clips for sequences."""
    job_id: UUID
    clip_indices: List[int] = Field(description="Indices of clips to analyze")


class SequenceClip(BaseModel):
    """Single clip within a sequence."""
    index: int
    caption: str
    cliffhanger_score: float = Field(
        ge=0, le=1, description="How well this clip ends on a hook"
    )
    next_part_hook: Optional[str] = None


class ClipSequenceResponse(BaseModel):
    """Recommended sequence from clips."""
    sequence_id: UUID
    job_id: UUID
    sequence_title: str
    series_description: str
    clips: List[SequenceClip]
    total_duration_seconds: float
    viability_score: float = Field(
        ge=0, le=1, description="How well-connected this sequence is"
    )
    recommended_publish_strategy: str = Field(
        description="daily, 24h_apart, 48h_apart, etc"
    )
    platform_optimizations: dict = Field(
        description="Platform-specific captions, hashtags, thumbnails"
    )


class SequenceListResponse(BaseModel):
    """Multiple detected sequences for a job."""
    job_id: UUID
    total_sequences: int
    top_sequence: ClipSequenceResponse
    all_sequences: List[ClipSequenceResponse]


class SequencePublishRequest(BaseModel):
    """Publish a sequence across social platforms."""
    sequence_id: UUID
    platforms: List[str] = Field(description="tiktok, instagram, youtube")
    start_immediately: bool = Field(
        default=False, description="Publish first clip now"
    )
    publish_interval_hours: int = Field(
        default=24, description="Hours between each part"
    )
    hashtags_override: Optional[List[str]] = None


class SequencePublishResponse(BaseModel):
    """Confirmation of sequence publishing."""
    sequence_id: UUID
    publish_plan: List[dict] = Field(
        description="List of clips with their scheduled publish times"
    )
    total_scheduled: int
    first_publish_at: datetime
    last_publish_at: datetime
