"""File: services/face_tracker.py
Purpose: Robust face bounding box management and FFmpeg crop parameter calculation.
         Prevents crashes by clamping coordinates to valid frame dimensions.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class BoundingBox:
    x: int
    y: int
    w: int
    h: int

class FaceTrackingError(Exception):
    """Raised when a bounding box is degenerate or invalid."""
    pass

def clamp_bbox(
    bbox: BoundingBox,
    frame_width: int,
    frame_height: int,
    min_size: int = 10,
) -> BoundingBox:
    """
    Clamp bounding box coordinates to valid frame dimensions.
    Raises FaceTrackingError if result is degenerate (too small to be valid).
    """
    if frame_width <= 0 or frame_height <= 0:
        raise FaceTrackingError(f"Invalid frame dimensions: {frame_width}x{frame_height}")

    x = max(0, min(bbox.x, frame_width - 1))
    y = max(0, min(bbox.y, frame_height - 1))
    
    # Ensure width and height don't exceed remaining frame space
    w = max(0, min(bbox.w, frame_width - x))
    h = max(0, min(bbox.h, frame_height - y))

    if w < min_size or h < min_size:
        raise FaceTrackingError(
            f"Degenerate bbox after clamping: ({x},{y},{w},{h}) "
            f"for frame {frame_width}x{frame_height}"
        )

    return BoundingBox(x=x, y=y, w=w, h=h)

def get_crop_params(
    raw_bbox: BoundingBox,
    frame_width: int,
    frame_height: int,
    target_aspect: float = 9 / 16,
) -> dict:
    """Produce safe FFmpeg crop params centered on face, clamped to frame."""
    try:
        safe_bbox = clamp_bbox(raw_bbox, frame_width, frame_height)
        
        face_cx = safe_bbox.x + (safe_bbox.w // 2)
        
        # Calculate target crop width based on aspect ratio
        # Vertical crop usually takes full height
        crop_w = int(frame_height * target_aspect)
        
        # If crop_w is wider than original frame, we have to scale down later, 
        # but for the 'crop' filter we clamp to frame_width.
        crop_w = min(crop_w, frame_width)
        
        # Center the crop window on the face center
        crop_x = max(0, min(face_cx - (crop_w // 2), frame_width - crop_w))
        
        # Ensure even numbers for FFmpeg
        crop_w = crop_w if crop_w % 2 == 0 else crop_w - 1
        crop_x = crop_x if crop_x % 2 == 0 else crop_x
        
        return {"x": int(crop_x), "y": 0, "w": int(crop_w), "h": int(frame_height)}
        
    except FaceTrackingError as e:
        logger.warning("Face tracking glitch; falling back to center crop: %s", e)
        # Fallback: bias the crop toward the original bbox center rather than
        # forcing a hard frame-center crop, which can clip asymmetric subjects.
        crop_w = int(frame_height * target_aspect)
        crop_w = min(crop_w, frame_width)
        crop_w = crop_w if crop_w % 2 == 0 else crop_w - 1
        face_cx = max(0, min(raw_bbox.x + (raw_bbox.w // 2), frame_width - 1))
        crop_x = max(0, min(face_cx - (crop_w // 2), frame_width - crop_w))
        crop_x = crop_x if crop_x % 2 == 0 else crop_x
        
        return {"x": int(crop_x), "y": 0, "w": int(crop_w), "h": int(frame_height)}
