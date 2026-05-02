"""File: services/layout_engine.py
Purpose: Modular video layout engine supporting Vertical and Split-Screen (Podcast) modes.
"""

from __future__ import annotations
import logging
from typing import Literal, List

logger = logging.getLogger(__name__)

LayoutType = Literal["vertical", "split_screen", "speaker_screen", "screen_only", "pip"]

class LayoutEngine:
    """Generates FFmpeg filtergraphs for different social media layouts."""

    @classmethod
    def get_filtergraph(
        cls, 
        layout_type: LayoutType, 
        width: int, 
        height: int, 
        subject_centers: List[float],
        screen_focus: str = "center",
    ) -> str:
        """
        Build the filtergraph string based on layout and face positions.
        - subject_centers: List of X-coordinates for detected subjects.
        """
        subject_centers = [float(center) for center in subject_centers if center is not None]

        if layout_type == "screen_only":
            return cls._screen_only_filter(width, height, screen_focus=screen_focus)

        if layout_type == "speaker_screen":
            return cls._speaker_screen_filter(
                width,
                height,
                subject_centers[0] if subject_centers else width / 2,
                screen_focus=screen_focus,
            )

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
    def _ensure_even(value: int) -> int:
        return value if value % 2 == 0 else value - 1

    @classmethod
    def _crop_width_for_ratio(cls, width: int, height: int, ratio: float) -> int:
        target_w = min(width, int(height * ratio))
        target_w = cls._ensure_even(max(2, target_w))
        return min(target_w, cls._ensure_even(width))

    @staticmethod
    def _focus_crop_x(width: int, crop_width: int, *, focus: str = "center", x_center: float | None = None) -> int:
        if x_center is not None:
            proposed = int(x_center - (crop_width / 2))
        elif focus == "left":
            proposed = 0
        elif focus == "right":
            proposed = width - crop_width
        else:
            proposed = int((width - crop_width) / 2)
        return max(0, min(width - crop_width, proposed))

    @staticmethod
    def _vertical_filter(width: int, height: int, x_center: float) -> str:
        """Standard 9:16 vertical crop centered on subject with safety clamping."""
        crop_width = LayoutEngine._crop_width_for_ratio(width, height, 9 / 16)
        crop_x = LayoutEngine._focus_crop_x(width, crop_width, x_center=x_center)
        return f"crop={crop_width}:{height}:{crop_x}:0"

    @staticmethod
    def _screen_only_filter(width: int, height: int, screen_focus: str) -> str:
        target_w = LayoutEngine._crop_width_for_ratio(width, height, 9 / 16)
        x = LayoutEngine._focus_crop_x(width, target_w, focus=screen_focus)
        return f"crop={target_w}:{height}:{x}:0"

    @staticmethod
    def _split_screen_filter(width: int, height: int, x1: float, x2: float) -> str:
        """Stacked split screen (Host/Guest) with safety clamping."""
        half_h = int(height / 2)
        half_h = LayoutEngine._ensure_even(half_h)
        crop_w = LayoutEngine._crop_width_for_ratio(width, half_h, 9 / 8)
        crop1_x = LayoutEngine._focus_crop_x(width, crop_w, x_center=x1)
        crop2_x = LayoutEngine._focus_crop_x(width, crop_w, x_center=x2)

        # Filtergraph: 
        # 1. Split input into two streams
        # 2. Crop top stream around subject 1
        # 3. Crop bottom stream around subject 2
        # 4. Vertical stack
        filter_str = (
            f"[0:v]split=2[top_raw][bot_raw]; "
            f"[top_raw]crop={crop_w}:{half_h}:{crop1_x}:0[top]; "
            f"[bot_raw]crop={crop_w}:{half_h}:{crop2_x}:0[bot]; "
            f"[top][bot]vstack=inputs=2"
        )
        return filter_str

    @staticmethod
    def _speaker_screen_filter(width: int, height: int, x_center: float, screen_focus: str) -> str:
        """Top speaker strip plus screen-dominant lower panel."""
        output_width = 1080
        output_height = 1920
        speaker_h = LayoutEngine._ensure_even(int(output_height * 0.35))
        screen_h = output_height - speaker_h

        speaker_crop_w = LayoutEngine._crop_width_for_ratio(width, height, output_width / speaker_h)
        screen_crop_w = LayoutEngine._crop_width_for_ratio(width, height, output_width / screen_h)

        speaker_x = LayoutEngine._focus_crop_x(width, speaker_crop_w, x_center=x_center)
        screen_x = LayoutEngine._focus_crop_x(width, screen_crop_w, focus=screen_focus)

        return (
            f"[0:v]split=2[speaker_raw][screen_raw]; "
            f"[speaker_raw]crop={speaker_crop_w}:{height}:{speaker_x}:0,scale={output_width}:{speaker_h}[speaker]; "
            f"[screen_raw]crop={screen_crop_w}:{height}:{screen_x}:0,scale={output_width}:{screen_h}[screen]; "
            f"[speaker][screen]vstack=inputs=2"
        )
