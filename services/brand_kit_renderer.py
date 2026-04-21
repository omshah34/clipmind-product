"""File: services/brand_kit_renderer.py
Purpose: Converts BrandKitRecord to SubtitleStyle and handles watermark/overlay
         rendering logic for branded video output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import logging

from api.models.brand_kit import BrandKitRecord
from services.video_processor import SubtitleStyle

logger = logging.getLogger(__name__)


def brand_kit_to_subtitle_style(brand_kit: BrandKitRecord) -> SubtitleStyle:
    """Convert a BrandKitRecord to a SubtitleStyle for video rendering.
    
    This bridges the database brand kit configuration with the video processor's
    internal SubtitleStyle class.
    """
    return SubtitleStyle(
        font_name=brand_kit.font_name,
        font_size=brand_kit.font_size,
        bold=brand_kit.bold,
        alignment=brand_kit.alignment,
        primary_colour=brand_kit.primary_colour,
        outline_colour=brand_kit.outline_colour,
        outline=brand_kit.outline,
    )


def build_watermark_filter(watermark_url: Optional[str], video_width: int = 1080, video_height: int = 1920) -> str:
    """Build an FFmpeg filter string for watermark overlay.
    
    Watermark is positioned at bottom-right corner with 10px padding.
    Assumes watermark is a PNG with transparency.
    
    Args:
        watermark_url: URL or path to watermark image
        video_width: Video width in pixels
        video_height: Video height in pixels
    
    Returns:
        FFmpeg filter string, or empty string if no watermark
    """
    if not watermark_url:
        return ""
    
    # Escape for FFmpeg filter syntax
    escaped_path = watermark_url.replace("'", "'\\''")
    
    # Position: bottom-right with 10px padding
    # (W-w-10):(H-h-10) = x:y coordinates
    watermark_filter = (
        f"[0:v][wm]overlay="
        f"(W-w-10):(H-h-10):enable='between(t,0,n)'"
        f"[v]"
    )
    
    # Would need to chain input for watermark file
    # This is a placeholder — full implementation requires input handling in video_processor
    return watermark_filter


def build_intros_outros_filter(
    intro_url: Optional[str],
    outro_url: Optional[str],
    clip_duration: float,
) -> str:
    """Build filter string for intro/outro bumpers.
    
    This is a placeholder for more complex concatenation logic.
    Full implementation requires:
    - Downloading intro/outro clips
    - Concatenating: intro + clip + outro
    - Handling audio mixing
    
    Returns:
        FFmpeg filter string or empty string
    """
    if not intro_url and not outro_url:
        return ""
    
    # This would typically use the concat demuxer in FFmpeg
    # [0:v][0:a][1:v][1:a][2:v][2:a]concat=n=3:v=1:a=1[outv][outa]
    # where 0 = intro, 1 = clip, 2 = outro
    
    logger.warning("Intro/outro rendering not yet implemented")
    return ""
