"""File: api/models/content_dna.py
Purpose: Pydantic models for Content DNA (personalized AI learning)
"""

from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, List, Dict
from datetime import datetime


class ContentSignalRequest(BaseModel):
    """Log a user signal (download, skip, edit, publish, etc)."""
    job_id: UUID
    clip_index: int
    signal_type: str = Field(
        description="downloaded, skipped, edited, regenerated, published"
    )
    signal_metadata: Optional[Dict] = None


class ContentSignalResponse(BaseModel):
    """Recorded signal."""
    id: UUID
    job_id: UUID
    clip_index: int
    signal_type: str
    signal_count: int = Field(description="Signals collected for this user")
    confidence_score: float = Field(
        description="0-1, how confident the personalization is"
    )
    created_at: datetime


class UserScoreWeightsResponse(BaseModel):
    """User's personalized clip scoring weights."""
    user_id: UUID
    weights: Dict[str, float]
    signal_count: int
    confidence_score: float = Field(
        description="0-1, increases as more signals collected"
    )
    learning_status: str = Field(
        description="learning, converging, optimized"
    )
    progress_percent: int = Field(ge=0, le=100)
    last_updated: datetime


class PersonalizationInsightResponse(BaseModel):
    """Insights about what the AI has learned about the user."""
    preferred_clip_length_seconds: Optional[int]
    top_scoring_dimensions: List[str]
    underutilized_dimensions: List[str]
    most_downloaded_style: Optional[str]
    recommendation: str
    next_milestone_signals: int
