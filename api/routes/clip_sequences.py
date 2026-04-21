"""File: api/routes/clip_sequences.py
Purpose: Clip sequence endpoints (stub — ready for implementation).
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/clip-sequences", tags=["clip_sequences"])


@router.get("/")
def list_clip_sequences() -> dict:
    return {"sequences": []}
