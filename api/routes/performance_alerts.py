"""File: api/routes/performance_alerts.py
Purpose: API endpoints for performance alerts and proactive insights.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID

from api.dependencies import get_current_user, AuthenticatedUser
from db.repositories.performance import get_performance_alerts, mark_alerts_as_read

router = APIRouter(prefix="/performance/alerts", tags=["Performance"])

@router.get("/")
async def list_alerts(
    unread_only: bool = True,
    limit: int = Query(20, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_current_user)
):
    """List recent performance alerts/insights for the user."""
    user_id = str(user.user_id)
    alerts = get_performance_alerts(user_id, unread_only=unread_only, limit=limit)
    return alerts

@router.patch("/read")
async def mark_read(
    alert_ids: Optional[List[str]] = Query(None),
    read_all: bool = False,
    user: AuthenticatedUser = Depends(get_current_user)
):
    """Mark specific alerts or all alerts as read."""
    user_id = str(user.user_id)
    if not read_all and not alert_ids:
        raise HTTPException(status_code=400, detail="Must provide alert_ids or set read_all=True")
    
    count = mark_alerts_as_read(user_id, alert_ids if not read_all else "all")
    return {"status": "success", "count": count}
