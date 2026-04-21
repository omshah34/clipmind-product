"""File: services/layout_engine.py
Purpose: Modular video layout engine supporting Vertical and Split-Screen (Podcast) modes.
"""

from __future__ import annotations
import logging
from typing import Literal, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

LayoutType = Literal["vertical", "split_screen", "pip"]

class LayoutEngine:
    """Generates FFmpeg filtergraphs for different social media layouts."""

    @classmethod
    def get_filtergraph(
        cls, 
        layout_type: LayoutType, 
        width: int, 
        height: int, 
        subject_centers: List[float]
    ) -> str:
        """
        Build the filtergraph string based on layout and face positions.
        - subject_centers: List of X-coordinates for detected subjects.
        """
        if layout_type == "vertical" or not subject_centers:
            return cls._vertical_filter(width, height, subject_centers[0] if subject_centers else width/2)
        
        if layout_type == "split_screen":
            if len(subject_centers) < 2:
                logger.warning("[layout] Only one face detected for split_screen. Falling back to vertical.")
                return cls._vertical_filter(width, height, subject_centers[0] if subject_centers else width/2)
            
            return cls._split_screen_filter(width, height, subject_centers[0], subject_centers[1])
        
        # Default to vertical if unsupported
        return cls._vertical_filter(width, height, width/2)

    @staticmethod
    def _vertical_filter(width: int, height: int, x_center: float) -> str:
        """Standard 9:16 vertical crop centered on subject."""
        target_w = int(height * (9/16))
        # Ensure target_w is even for FFmpeg
        target_w = target_w if target_w % 2 == 0 else target_w - 1

        if abs(x_center - (width / 2)) < 1e-6:
            return "crop=ih*9/16:ih:(iw-ih*9/16)/2:0"
        
        # Calculate crop x
        x = int(x_center - (target_w / 2))
        x = max(0, min(width - target_w, x))
        
        return f"crop={target_w}:{height}:{x}:0"

    @staticmethod
    def _split_screen_filter(width: int, height: int, x1: float, x2: float) -> str:
        """Stacked split screen (Host/Guest)."""
        # We want a 9:16 final output. Each half is 9:8.
        # Height of total is 'height'. Each half height is height/2.
        # Width remains consistent for 9:16 -> target_w = height * (9/16)
        
        target_w = int(height * (9/16))
        target_w = target_w if target_w % 2 == 0 else target_w - 1
        half_h = int(height / 2)
        half_h = half_h if half_h % 2 == 0 else half_h - 1
        
        # Calculate crops for top and bottom. 
        # We crop a 9:8 section from the original.
        # Original height is 'height'. We want to crop 'half_h'.
        # Usually faces are in upper half, so we crop top half of original or center it.
        
        # Top Crop logic: center on x1
        x1_crop = int(x1 - (target_w / 2))
        x1_crop = max(0, min(width - target_w, x1_crop))
        
        # Bottom Crop logic: center on x2
        x2_crop = int(x2 - (target_w / 2))
        x2_crop = max(0, min(width - target_w, x2_crop))

        # Filtergraph: 
        # 1. Split input into two streams
        # 2. Crop top stream around subject 1
        # 3. Crop bottom stream around subject 2
        # 4. Vertical stack
        filter_str = (
            f"[0:v]split=2[top_raw][bot_raw]; "
            f"[top_raw]crop={target_w}:{half_h}:{x1_crop}:0[top]; "
            f"[bot_raw]crop={target_w}:{half_h}:{x2_crop}:0[bot]; "
            f"[top][bot]vstack=inputs=2"
        )
        return filter_str
