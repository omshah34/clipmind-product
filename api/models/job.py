"""File: api/models/job.py
Purpose: Canonical Pydantic models for all job-related data structures.
         All routes, workers, and services must import models from this file.
         Single source of truth for API request/response contracts.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
import uuid

from pydantic import BaseModel, model_validator
import json

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
    hook_headlines: List[str] = []
    refinement_reason: Optional[str] = None


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
    user_id: Optional[uuid.UUID] = None
    brand_kit_id: Optional[uuid.UUID] = None
    status: str
    source_video_url: str
    audio_url: Optional[str] = None
    transcript_json: Optional[dict] = None
    clips_json: Optional[List[ClipResult]] = None
    timeline_json: Optional[dict] = None
    failed_stage: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    prompt_version: str = "v4"
    estimated_cost_usd: float = 0.0
    actual_cost_usd: float = 0.0
    language: str = "en"
    is_rejected: bool = False
    rejected_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

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

    job_id: uuid.UUID
    status: str
    created_at: datetime


class DirectUploadInitRequest(BaseModel):
    filename: str
    size_bytes: int
    duration_seconds: float
    user_id: Optional[uuid.UUID] = None
    brand_kit_id: Optional[uuid.UUID] = None
    language: Optional[str] = "en"


class DirectUploadInitResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    created_at: datetime
    upload_url: str
    source_video_url: str


class DirectUploadCompleteRequest(BaseModel):
    job_id: uuid.UUID


class DirectUploadFailRequest(BaseModel):
    job_id: uuid.UUID
    message: str


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
