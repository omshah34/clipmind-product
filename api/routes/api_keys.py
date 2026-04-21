"""File: api/routes/api_keys.py
Purpose: API key management endpoints (stub — ready for implementation).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api-keys", tags=["api_keys"])


@router.get("/")
def list_api_keys() -> dict:
    return {"api_keys": []}
