"""File: api/routes/autopilot.py
Purpose: API routes for managing automated content ingestion and the publish queue.
"""

from __future__ import annotations

import logging
from uuid import UUID
from typing import Any

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text

from api.dependencies import get_current_user, AuthenticatedUser
from db.repositories.autopilot import (
    create_connected_source,
    list_active_sources,
    get_pending_publish_items,
    update_publish_status,
    engine,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/autopilot", tags=["autopilot"])

# --- Models ---

class ConnectedSourceCreate(BaseModel):
    name: str
    source_type: str = Field(..., description="e.g., 'youtube_channel', 'rss_feed'")
    config_json: dict = Field(default_factory=dict)

class PublishQueueItem(BaseModel):
    id: str
    job_id: str
    clip_index: int
    platform: str
    status: str
    scheduled_for: Any

# --- Routes ---

@router.get("/sources")
async def get_sources(user: AuthenticatedUser = Depends(get_current_user)):
    """List all active automated sources for the authenticated user."""
    sources = list_active_sources(str(user.user_id))
    return {"sources": sources}

@router.post("/sources", status_code=201)
async def link_source(
    payload: ConnectedSourceCreate,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Link a new content source for automation."""
    try:
        source = create_connected_source(
            user_id=str(user.user_id),
            name=payload.name,
            source_type=payload.source_type,
            config=payload.config_json
        )
        return source
    except Exception as exc:
        logger.error("Failed to create source: %s", exc)
        raise HTTPException(status_code=500, detail="Could not create source")

@router.get("/queue")
async def get_queue(user: AuthenticatedUser = Depends(get_current_user)):
    """View the upcoming publish queue for the authenticated user."""
    items = get_pending_publish_items(str(user.user_id))
    return {"queue": items}

@router.post("/queue/{item_id}/cancel")
async def cancel_publish(
    item_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Cancel a scheduled post."""
    with engine.connect() as connection:
        row = connection.execute(
            text("SELECT id FROM publish_queue WHERE id = :id AND user_id = :user_id"),
            {"id": item_id, "user_id": str(user.user_id)},
        ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Queue item not found")

    update_publish_status(item_id, "cancelled")
    return {"message": f"Item {item_id} cancelled"}
