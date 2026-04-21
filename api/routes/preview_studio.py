"""File: api/routes/preview_studio.py
Purpose: Preview studio endpoints (stub — ready for implementation).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/preview-studio", tags=["preview_studio"])


@router.get("/")
def list_previews() -> dict:
    return {"previews": []}
