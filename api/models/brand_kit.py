"""File: api/models/brand_kit.py
Purpose: Canonical Pydantic models for brand kit (branding/styling) data.
         All brand kit routes and services must import models from this file.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, Field, field_validator


class BrandKitCreate(BaseModel):
    """Request body for creating a new brand kit."""
    
    name: str = Field(default="My Brand", description="Friendly name for this brand kit")
    
    # Caption styling
    font_name: str = Field(default="Arial", description="Font name for captions")
    font_size: int = Field(default=22, ge=8, le=72, description="Font size for captions")
    bold: bool = Field(default=True, description="Make captions bold")
    alignment: int = Field(default=2, ge=1, le=9, description="ASS alignment (1-9)")
    primary_colour: str = Field(
        default="&H00FFFFFF",
        description="Primary color in ASS format (&HAABBGGRR)"
    )
    outline_colour: str = Field(
        default="&H00000000",
        description="Outline color in ASS format (&HAABBGGRR)"
    )
    outline: int = Field(default=2, ge=0, le=10, description="Outline thickness")
    
    # Watermark and overlays
    watermark_url: Optional[str] = Field(default=None, description="URL to watermark image")
    intro_clip_url: Optional[str] = Field(default=None, description="URL to intro video bumper")
    outro_clip_url: Optional[str] = Field(default=None, description="URL to outro video bumper")
    
    # Gap 72: Transcription vocab
    vocabulary_hints: Optional[list[str]] = Field(default=None, description="Custom words to bias Whisper toward")
    
    is_default: bool = Field(default=False, description="Set as default brand kit")
    
    @field_validator('font_name')
    @classmethod
    def validate_font_name(cls, v: str) -> str:
        if not v or len(v.strip()) == 0:
            raise ValueError("Font name cannot be empty")
        return v.strip()


class BrandKitUpdate(BaseModel):
    """Request body for updating an existing brand kit (all fields optional)."""
    
    name: Optional[str] = None
    font_name: Optional[str] = None
    font_size: Optional[int] = Field(default=None, ge=8, le=72)
    bold: Optional[bool] = None
    alignment: Optional[int] = Field(default=None, ge=1, le=9)
    primary_colour: Optional[str] = None
    outline_colour: Optional[str] = None
    outline: Optional[int] = Field(default=None, ge=0, le=10)
    watermark_url: Optional[str] = None
    intro_clip_url: Optional[str] = None
    outro_clip_url: Optional[str] = None
    vocabulary_hints: Optional[list[str]] = None
    is_default: Optional[bool] = None


class BrandKitRecord(BaseModel):
    """Full DB row shape. Returned in API responses."""
    
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    font_name: str
    font_size: int
    bold: bool
    alignment: int
    primary_colour: str
    outline_colour: str
    outline: int
    watermark_url: Optional[str]
    intro_clip_url: Optional[str]
    outro_clip_url: Optional[str]
    vocabulary_hints: Optional[list[str]]
    is_default: bool
    created_at: datetime
    updated_at: datetime


class BrandKitResponse(BaseModel):
    """Response shape for GET /brand-kits/{id}."""
    
    brand_kit: BrandKitRecord


class BrandKitListResponse(BaseModel):
    """Response shape for GET /brand-kits."""
    
    brand_kits: list[BrandKitRecord]
    total: int


class PresetBrandKit(BaseModel):
    """Predefined brand kit preset (not stored in DB)."""
    
    name: str
    description: str
    font_name: str
    font_size: int
    bold: bool
    alignment: int
    primary_colour: str
    outline_colour: str
    outline: int


# Preset brand kits (hardcoded defaults for users to choose from)
BRAND_KIT_PRESETS: dict[str, PresetBrandKit] = {
    "minimal_white": PresetBrandKit(
        name="Minimal White",
        description="Clean white captions with subtle outline",
        font_name="Arial",
        font_size=24,
        bold=True,
        alignment=2,
        primary_colour="&H00FFFFFF",  # white
        outline_colour="&H00000000",  # black
        outline=1,
    ),
    "bold_neon": PresetBrandKit(
        name="Bold Neon",
        description="High-contrast neon style for modern feel",
        font_name="Arial",
        font_size=28,
        bold=True,
        alignment=2,
        primary_colour="&H0000FFFF",  # yellow (BGR)
        outline_colour="&H00000000",  # black
        outline=3,
    ),
    "podcast_classic": PresetBrandKit(
        name="Podcast Classic",
        description="Traditional podcast captioning style",
        font_name="Trebuchet MS",
        font_size=22,
        bold=True,
        alignment=2,
        primary_colour="&H00FFFFFF",  # white
        outline_colour="&H00330033",  # dark purple
        outline=2,
    ),
    "minimal_bright": PresetBrandKit(
        name="Minimal Bright",
        description="High contrast for maximum readability",
        font_name="Verdana",
        font_size=26,
        bold=True,
        alignment=2,
        primary_colour="&H00FFFFFF",  # white
        outline_colour="&H00000000",  # black
        outline=4,
    ),
}
