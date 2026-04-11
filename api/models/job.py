from __future__ import annotations

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel


class ClipResult(BaseModel):
    clip_index: int
    start_time: float
    end_time: float
    duration: float
    clip_url: str
    hook_score: float
    emotion_score: float
    clarity_score: float
    story_score: float
    virality_score: float
    final_score: float
    reason: str


class ClipSummary(BaseModel):
    """Lightweight version returned in status polling responses."""

    clip_index: int
    clip_url: str
    duration: float
    final_score: float
    reason: str


class JobRecord(BaseModel):
    """Full DB row shape. Used internally in workers and services."""

    id: uuid.UUID
    status: str
    source_video_url: str
    audio_url: Optional[str] = None
    transcript_json: Optional[dict] = None
    clips_json: Optional[List[ClipResult]] = None
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    prompt_version: str = "v1"
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    created_at: datetime
    updated_at: datetime


class UploadResponse(BaseModel):
    """Response shape for POST /upload."""

    job_id: uuid.UUID
    status: str
    created_at: datetime


class JobStatusResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/status."""

    job_id: uuid.UUID
    status: str
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    clips: Optional[List[ClipSummary]] = None


class JobClipsResponse(BaseModel):
    """Response shape for GET /jobs/{job_id}/clips."""

    job_id: uuid.UUID
    clips: List[ClipResult]


class ErrorResponse(BaseModel):
    """Standard error shape for all 4xx responses."""

    error: str
    message: str
