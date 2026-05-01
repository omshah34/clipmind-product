# File: api/routes/analytics.py
from fastapi import APIRouter, HTTPException, Depends
from db.connection import analytics_engine
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
import asyncio
import logging

router = APIRouter(prefix="/v1/analytics", tags=["Analytics"])
logger = logging.getLogger(__name__)

def _fetch_analytics_sync(user_id: str) -> dict:
    """Heavy aggregation query executed on the analytics engine."""
    with analytics_engine.connect() as conn:
        # Example heavy query for dashboard stats
        query = text("""
            SELECT 
                COUNT(*) as total_clips,
                AVG(virality_score) as avg_virality,
                SUM(duration) as total_duration
            FROM clips 
            WHERE user_id = :user_id
        """)
        result = conn.execute(query, {"user_id": user_id}).mappings().first()
        return dict(result) if result else {"total_clips": 0, "avg_virality": 0, "total_duration": 0}

@router.get("/summary")
async def get_analytics_summary(user_id: str):
    """
    Gap 364: Fetch analytics with timeout protection and pool isolation.
    """
    try:
        # Run in thread pool to avoid blocking the FastAPI event loop
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: _fetch_analytics_sync(user_id)
        )
        return result
    except OperationalError as e:
        if "statement timeout" in str(e).lower():
            logger.error(f"Analytics query timed out for user {user_id}")
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "CM-5001",
                    "message": "Analytics temporarily unavailable due to high load.",
                    "retry_after": 30,
                }
            )
        logger.error(f"Database error in analytics: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
