"""File: api/routes/campaigns.py
Purpose: Campaign management endpoints with real CRUD, uploads, stats, and calendar data.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from api.dependencies import AuthenticatedUser, get_current_user
from api.routes.upload import (
    UploadValidationError,
    estimate_job_cost,
    get_video_duration_seconds,
    save_upload_to_temp,
    validate_upload_constraints,
)
from core.config import settings
from db.repositories.campaigns import create_campaign, delete_campaign, get_campaign, list_campaigns, update_campaign
from db.repositories.jobs import create_job
from db.connection import engine
from db.repositories.jobs import update_job
from services.storage import storage_service
from services.task_queue import dispatch_task
from workers.pipeline import process_job

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


class CampaignCreatePayload(BaseModel):
    name: str
    description: str | None = None
    schedule_config: dict | None = None


class CampaignUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None
    schedule_config: dict | None = None


def _normalize_campaign(record: dict) -> dict:
    data = dict(record)
    schedule_config = data.get("schedule_config")
    if isinstance(schedule_config, str):
        try:
            data["schedule_config"] = json.loads(schedule_config)
        except json.JSONDecodeError:
            data["schedule_config"] = {}
    data.setdefault("clip_count", 0)
    return data


def _load_campaign_jobs(campaign_id: str) -> list[dict]:
    query = text(
        """
        SELECT id, created_at, scheduled_publish_date, clips_json
        FROM jobs
        WHERE campaign_id = :campaign_id
        ORDER BY created_at ASC
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"campaign_id": campaign_id}).fetchall()

    jobs: list[dict] = []
    for row in rows:
        job = dict(row._mapping)
        clips_json = job.get("clips_json")
        if isinstance(clips_json, str):
            try:
                job["clips_json"] = json.loads(clips_json)
            except json.JSONDecodeError:
                job["clips_json"] = []
        jobs.append(job)
    return jobs


def _campaign_stats(campaign_id: str) -> dict:
    jobs = _load_campaign_jobs(campaign_id)

    total_videos_uploaded = len(jobs)
    total_clips_detected = 0
    clips_scheduled = 0
    clips_published = 0
    score_total = 0.0
    score_count = 0
    next_publish_date: datetime | None = None

    with engine.connect() as connection:
        published_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM published_clips
                WHERE user_id = (
                    SELECT user_id FROM campaigns WHERE id = :campaign_id LIMIT 1
                )
                AND job_id IN (SELECT id FROM jobs WHERE campaign_id = :campaign_id)
                """
            ),
            {"campaign_id": campaign_id},
        ).scalar() or 0

    for job in jobs:
        clips = job.get("clips_json") or []
        scheduled_at = job.get("scheduled_publish_date")
        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            except ValueError:
                scheduled_at = None
        if scheduled_at and scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

        total_clips_detected += len(clips)
        if scheduled_at:
            clips_scheduled += len(clips)
            if next_publish_date is None or scheduled_at < next_publish_date:
                next_publish_date = scheduled_at

        for clip in clips:
            score = clip.get("final_score")
            if score is not None:
                score_total += float(score)
                score_count += 1

    clips_published = int(published_count)
    avg_clip_score = score_total / score_count if score_count else 0.0

    return {
        "campaign_id": campaign_id,
        "total_videos_uploaded": total_videos_uploaded,
        "total_clips_detected": total_clips_detected,
        "clips_scheduled": clips_scheduled,
        "clips_published": clips_published,
        "next_publish_date": next_publish_date,
        "avg_clip_score": avg_clip_score,
    }


@router.get("/")
def list_user_campaigns(
    user: AuthenticatedUser = Depends(get_current_user),
    limit: int = 20,
    offset: int = 0,
    status: str | None = None,
) -> dict:
    campaigns, total = list_campaigns(user.user_id, limit=limit, offset=offset, status=status)

    enriched = []
    for campaign in campaigns:
        campaign_id = str(campaign["id"])
        jobs = _load_campaign_jobs(campaign_id)
        campaign["clip_count"] = sum(len(job.get("clips_json") or []) for job in jobs)
        enriched.append(_normalize_campaign(campaign))

    return {"campaigns": enriched, "total": int(total or 0), "limit": limit, "offset": offset}


@router.post("/")
def create_new_campaign(
    payload: CampaignCreatePayload,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = create_campaign(
        user_id=user.user_id,
        name=payload.name,
        description=payload.description,
        schedule_config=payload.schedule_config,
    )
    campaign["clip_count"] = 0
    return _normalize_campaign(campaign)


@router.get("/{campaign_id}")
def read_campaign(
    campaign_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    campaign["clip_count"] = sum(len(job.get("clips_json") or []) for job in _load_campaign_jobs(campaign_id))
    return _normalize_campaign(campaign)


@router.patch("/{campaign_id}")
def edit_campaign(
    campaign_id: str,
    payload: CampaignUpdatePayload,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    updated = update_campaign(
        campaign_id,
        name=payload.name,
        description=payload.description,
        schedule_config=payload.schedule_config,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Campaign not found")
    updated["clip_count"] = sum(len(job.get("clips_json") or []) for job in _load_campaign_jobs(campaign_id))
    return _normalize_campaign(updated)


@router.delete("/{campaign_id}")
def remove_campaign(
    campaign_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    deleted = delete_campaign(campaign_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return {"status": "deleted", "campaign_id": campaign_id}


@router.post("/{campaign_id}/upload")
async def batch_upload_to_campaign(
    campaign_id: str,
    files: list[UploadFile] = File(...),
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    uploaded_jobs: list[str] = []
    errors: list[dict[str, str]] = []

    for file in files:
        temp_path: Path | None = None
        try:
            if not file.filename:
                raise UploadValidationError("invalid_file", "A video file is required.")

            temp_path, size_bytes = await save_upload_to_temp(file)
            duration_seconds = get_video_duration_seconds(temp_path)
            validate_upload_constraints(file.filename, size_bytes, duration_seconds)

            source_video_url = storage_service.upload_file(temp_path, "uploads", file.filename)
            estimated_cost_usd = estimate_job_cost(duration_seconds)
            job = create_job(
                source_video_url=source_video_url,
                prompt_version=settings.clip_prompt_version,
                estimated_cost_usd=estimated_cost_usd,
                user_id=str(user.user_id),
                language="en",
            )
            update_job(job.id, campaign_id=campaign_id)

            dispatch_task(
                process_job,
                str(job.id),
                fallback=lambda job_id: process_job.apply(args=(job_id,), throw=True),
                task_name="workers.pipeline.process_job",
            )
            uploaded_jobs.append(str(job.id))
        except UploadValidationError as exc:
            errors.append({"filename": file.filename or "unknown", "error": exc.message})
        except Exception as exc:
            errors.append({"filename": file.filename or "unknown", "error": str(exc)})
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)

    return {
        "campaign_id": campaign_id,
        "uploaded_jobs": uploaded_jobs,
        "total_uploaded": len(uploaded_jobs),
        "errors": errors,
        "message": "Upload complete" if uploaded_jobs else "No files uploaded",
    }


@router.get("/{campaign_id}/calendar")
def campaign_calendar(
    campaign_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    days_ahead: int = 30,
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")

    jobs = _load_campaign_jobs(campaign_id)
    clips_by_date: dict[str, list[dict]] = defaultdict(list)
    interval_days = 1
    schedule_config = campaign.get("schedule_config") or {}
    if isinstance(schedule_config, dict):
        interval_days = int(schedule_config.get("publish_interval_days", 1) or 1)

    now = datetime.now(timezone.utc)
    range_end = now + timedelta(days=days_ahead)

    for job in jobs:
        clips = job.get("clips_json") or []
        scheduled_at = job.get("scheduled_publish_date")
        if isinstance(scheduled_at, str):
            try:
                scheduled_at = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            except ValueError:
                scheduled_at = None
        if scheduled_at and scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)

        for index, clip in enumerate(clips):
            clip_schedule = scheduled_at or (now + timedelta(days=index * interval_days))
            if clip_schedule > range_end:
                continue

            date_key = clip_schedule.date().isoformat()
            clips_by_date[date_key].append(
                {
                    "job_id": job["id"],
                    "campaign_id": campaign_id,
                    "clip_index": clip.get("clip_index", index),
                    "start_time": clip.get("start_time", 0),
                    "end_time": clip.get("end_time", 0),
                    "duration": clip.get("duration", 0),
                    "final_score": clip.get("final_score", 0),
                    "reason": clip.get("reason", ""),
                    "scheduled_publish_date": clip_schedule.isoformat(),
                }
            )

    return {
        "campaign_id": campaign_id,
        "clips_by_date": dict(clips_by_date),
        "total_scheduled_clips": sum(len(items) for items in clips_by_date.values()),
        "date_range_start": now.isoformat(),
        "date_range_end": range_end.isoformat(),
    }


@router.get("/{campaign_id}/stats")
def campaign_stats(
    campaign_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
) -> dict:
    campaign = get_campaign(campaign_id)
    if not campaign or str(campaign.get("user_id")) != str(user.user_id):
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _campaign_stats(campaign_id)
