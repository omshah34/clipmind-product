"""File: api/routes/billing.py
Purpose: Billing and usage endpoints with real usage counts.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.dependencies import AuthenticatedUser, get_current_user
from db.connection import engine

router = APIRouter(tags=["billing"])


def _plan_limit(plan_tier: str) -> int:
    if plan_tier in {"pro", "business", "enterprise"}:
        return 1000
    if plan_tier in {"starter", "growth"}:
        return 250
    return 50


def _get_usage_counts(user_id: str) -> dict:
    with engine.connect() as connection:
        job_rows = connection.execute(
            text("SELECT clips_json, status FROM jobs WHERE user_id = :user_id"),
            {"user_id": user_id},
        ).fetchall()
        published_count = connection.execute(
            text("SELECT COUNT(*) FROM published_clips WHERE user_id = :user_id AND status = 'published'"),
            {"user_id": user_id},
        ).scalar() or 0
        queued_count = connection.execute(
            text("SELECT COUNT(*) FROM publish_queue WHERE user_id = :user_id AND status IN ('pending', 'processing')"),
            {"user_id": user_id},
        ).scalar() or 0

    clips_generated = 0
    videos_processed = len(job_rows)
    for row in job_rows:
        clips_json = row._mapping.get("clips_json")
        if isinstance(clips_json, str):
            try:
                clips_json = json.loads(clips_json)
            except json.JSONDecodeError:
                clips_json = []
        clips_generated += len(clips_json or [])

    return {
        "videos_processed": videos_processed,
        "clips_generated": clips_generated,
        "clips_published": int(published_count),
        "clips_queued": int(queued_count),
    }


@router.get("/status")
def billing_status(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    user_id = str(user.user_id)
    with engine.connect() as connection:
        subscription = connection.execute(
            text(
                """
                SELECT plan_tier, status, current_period_end, cancel_at_period_end
                FROM subscriptions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).one_or_none()

    plan_tier = (subscription.plan_tier if subscription else "free") or "free"
    subscription_status = (subscription.status if subscription else "active") or "active"
    usage = _get_usage_counts(user_id)
    limit = _plan_limit(plan_tier)
    used = usage["clips_generated"]

    return {
        "plan": plan_tier,
        "status": subscription_status,
        "clips_used": used,
        "clips_limit": limit,
        "clips_remaining": max(limit - used, 0),
        "current_period_end": subscription.current_period_end if subscription else None,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end) if subscription else False,
    }


@router.get("/usage")
def billing_usage(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    user_id = str(user.user_id)
    with engine.connect() as connection:
        subscription = connection.execute(
            text(
                """
                SELECT plan_tier, status
                FROM subscriptions
                WHERE user_id = :user_id
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).one_or_none()

    plan_tier = (subscription.plan_tier if subscription else "free") or "free"
    usage = _get_usage_counts(user_id)
    limit = _plan_limit(plan_tier)

    return {
        **usage,
        "clips_limit": limit,
        "clips_remaining": max(limit - usage["clips_generated"], 0),
        "plan": plan_tier,
        "status": (subscription.status if subscription else "active") or "active",
        "checked_at": datetime.now(timezone.utc),
    }


@router.post("/webhook")
def billing_webhook() -> dict:
    return {"received": True}
