"""File: api/routes/webhooks.py
Purpose: Webhook receiver endpoints (stub — ready for implementation).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/")
def receive_webhook(payload: dict = {}) -> dict:
    return {"received": True}
