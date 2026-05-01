"""File: api/models/job.py
Purpose: Canonical Pydantic models for all job-related data structures.
         All routes, workers, and services must import models from this file.
         Single source of truth for API request/response contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, Field, model_validator, field_validator
import json

# Gap 76: Import sanitization utility for XSS prevention
from core.sanitize import sanitize_text, sanitize_list


class ClipResult(BaseModel):
    clip_index: int
    start_time: float
    end_time: float
    duration: float
    clip_url: str = Field(max_length=2048)
    srt_url: Optional[str] = Field(default=None, max_length=2048)
    hook_score: float
    emotion_score: float
    clarity_score: float
    story_score: float
    virality_score: float
    final_score: float
    score_source: str = Field(default="llm", max_length=32)
    score_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reason: str = Field(max_length=2000)
    hook_headlines: List[str] = Field(default_factory=list)
    layout_type: Optional[str] = Field(default=None, max_length=64)
    visual_mode: Optional[str] = Field(default=None, max_length=64)
    selected_hook: Optional[str] = Field(default=None, max_length=300)
    render_recipe: Optional[dict] = None
    refinement_reason: Optional[str] = Field(default=None, max_length=2000)

    # Gap 76: Sanitize LLM-generated text fields to prevent stored XSS
    @field_validator("reason", "refinement_reason", "selected_hook", mode="before")
    @classmethod
    def sanitize_reason(cls, v):
        return sanitize_text(str(v)) if v is not None else v

    @field_validator("hook_headlines", mode="before")
    @classmethod
    def sanitize_headlines(cls, v):
        return sanitize_list(v) if isinstance(v, list) else v

    @field_validator("hook_headlines")
    @classmethod
    def validate_headline_lengths(cls, value: list[str]) -> list[str]:
        for headline in value:
            if len(headline) > 300:
                raise ValueError("Hook headlines must be 300 characters or fewer.")
        return value


class ClipSummary(BaseModel):
    """Lightweight version returned in status polling responses."""

    clip_index: int
    clip_url: str
    duration: float
    final_score: float
    reason: str


class JobRecord(BaseModel):
    """Full DB row shape. Used internally in workers and services."""

    id: str
    user_id: Optional[str] = None
    brand_kit_id: Optional[str] = None
    status: str
    source_video_url: str = Field(max_length=2048)
    proxy_video_url: Optional[str] = Field(default=None, max_length=2048)
    audio_url: Optional[str] = Field(default=None, max_length=2048)
    transcript_json: Optional[dict] = None
    clips_json: Optional[List[ClipResult]] = None
    timeline_json: Optional[dict] = None
    failed_stage: Optional[str] = Field(default=None, max_length=128)
    error_message: Optional[str] = Field(default=None, max_length=4000)
    retry_count: int = 0
    prompt_version: str = Field(default="v4", max_length=32)
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    language: str = Field(default="en", max_length=32)
    is_rejected: bool = False
    rejected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "user_id", "brand_kit_id", mode="before")
    @classmethod
    def stringify_uuid_fields(cls, value):
        return str(value) if isinstance(value, uuid.UUID) else value

    @model_validator(mode="before")
    @classmethod
    def parse_json_strings(cls, data: dict) -> dict:
        """Automatically parse any JSON strings provided for complex fields."""
        if isinstance(data, dict):
            json_fields = ["transcript_json", "clips_json", "timeline_json"]
            for field in json_fields:
                val = data.get(field)
                if isinstance(val, str):
                    try:
                        data[field] = json.loads(val)
                    except json.JSONDecodeError:
                        pass
        return data

class UploadResponse(BaseModel):
    """Response shape for POST /upload."""

    job_id: str
    status: str
    created_at: datetime


class DirectUploadInitRequest(BaseModel):
    filename: str = Field(max_length=255)
    size_bytes: int
    duration_seconds: float
    user_id: Optional[uuid.UUID] = None
    brand_kit_id: Optional[uuid.UUID] = None
    language: Optional[str] = Field(default="en", max_length=32)


class DirectUploadInitResponse(BaseModel):
    job_id: str
    status: str
    created_at: datetime
    upload_url: str
    source_video_url: str


class DirectUploadCompleteRequest(BaseModel):
    job_id: str


class DirectUploadFailRequest(BaseModel):
    job_id: str = Field(max_length=64)
    message: str = Field(max_length=1000)


class JobStatusResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/status."""

    job_id: str
    status: str
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    clips: Optional[List[ClipSummary]] = None


class JobClipsResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/clips."""

    job_id: str
    clips: List[ClipResult]


class JobListItem(BaseModel):
    id: str
    status: str
    source_video_url: str | None = None
    failed_stage: str | None = None
    error_message: str | None = None
    language: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    jobs: List[JobListItem]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    """Standard error shape for all 4xx/5xx responses.
    
    Gap 71: 'code' carries a machine-readable ClipMind error identifier (CM-XXXX).
    """

    error: str = Field(max_length=128)
    message: str = Field(max_length=1000)
    code: str | None = Field(default=None, max_length=32)  # Gap 71: e.g. "CM-4001"


class JobRejectionResponse(BaseModel):
    status: str
    message: str
    job_id: str


class ClipSearchResponse(BaseModel):
    status: str
    query: str = Field(max_length=512)
    results: List[ClipResult]
