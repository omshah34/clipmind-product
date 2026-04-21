"""File: api/models/preview_studio.py
Purpose: Pydantic models for Clip Preview Studio (in-browser preview + live caption editing)
"""

from pydantic import BaseModel, Field
from uuid import UUID
from typing import Optional, List
from datetime import datetime


class CaptionWord(BaseModel):
    """Individual word from Whisper with timing."""
    word: str
    start: float = Field(description="Start time in seconds")
    end: float = Field(description="End time in seconds")


class PreviewData(BaseModel):
    """Data needed for in-browser preview rendering."""
    job_id: UUID
    clip_index: int
    start_time: float = Field(description="Clip start in seconds")
    end_time: float = Field(description="Clip end in seconds")
    transcript_words: List[CaptionWord]
    current_srt: str = Field(description="Generated SRT subtitle data")
    duration_seconds: float


class CaptionEditRequest(BaseModel):
    """User edits to captions in preview studio."""
    job_id: UUID
    clip_index: int
    edited_srt: str = Field(description="Modified SRT with edited captions")
    edited_captions: List[str] = Field(description="Line-by-line edited captions")
    brand_kit_id: Optional[UUID] = None
    style_overrides: Optional[dict] = Field(
        None,
        description="Override specific caption style settings"
    )


class RenderRequest(BaseModel):
    """Request to render final clip with edited captions."""
    job_id: UUID
    clip_index: int
    edited_srt: str
    brand_kit_id: Optional[UUID] = None
    output_format: str = Field(default="mp4", description="mp4, mov, webm")
    output_quality: str = Field(default="1080p", description="1080p or 720p")


class RenderResponse(BaseModel):
    """Response from render request."""
    render_job_id: UUID
    job_id: UUID
    clip_index: int
    status: str = Field(description="queued, processing, completed, failed")
    estimated_time_seconds: int = Field(description="Estimated time to completion")
    created_at: datetime


class RenderStatusResponse(BaseModel):
    """Status of a rendering job."""
    render_job_id: UUID
    status: str
    progress_percent: Optional[int] = None
    output_url: Optional[str] = None
    error_message: Optional[str] = None
    completed_at: Optional[datetime] = None


class CaptionStyleRequest(BaseModel):
    """Request to preview caption style changes without rendering."""
    job_id: UUID
    clip_index: int
    brand_kit_id: Optional[UUID] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = None
    text_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    background_color: Optional[str] = Field(None, pattern="^#[0-9a-fA-F]{6}$")
    background_opacity: Optional[float] = Field(None, ge=0, le=1)
    position: Optional[str] = Field(None, description="top, middle, bottom")


class CaptionStyleResponse(BaseModel):
    """Preview of how caption style will look."""
    style_preview_url: str = Field(description="URL to preview image")
    style_applied: dict
