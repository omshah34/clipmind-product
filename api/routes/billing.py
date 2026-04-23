from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from api.dependencies import AuthenticatedUser, get_current_user
from core.config import settings

router = APIRouter(tags=['billing'])

def _guard_production():
    if settings.environment == "production":
        raise HTTPException(
            status_code=503, 
            detail="Billing service is currently being migrated. Please check back later."
        )

@router.get('/status')
def billing_status(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    _guard_production()
    return {
        'plan': 'pro',
        'status': 'active',
        'clips_used': 0,
        'clips_limit': 10000,
        'clips_remaining': 10000,
        'current_period_end': '2099-12-31T23:59:59Z',
        'cancel_at_period_end': False,
    }

@router.get('/usage')
def billing_usage(user: AuthenticatedUser = Depends(get_current_user)) -> dict:
    _guard_production()
    return {
        'videos_processed': 0,
        'clips_generated': 0,
        'clips_published': 0,
        'clips_queued': 0,
        'clips_limit': 10000,
        'clips_remaining': 10000,
        'plan': 'pro',
        'status': 'active',
        'checked_at': datetime.now(timezone.utc),
    }

@router.post('/webhook')
def billing_webhook() -> dict:
    return {'received': True}
