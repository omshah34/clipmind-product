"""File: services/visual_analyzer.py
Purpose: Memory-efficient frame extraction and visual feature analysis.
         Fixes 4K OOM by downsampling via FFmpeg pipes before loading into numpy.
"""

import logging
import subprocess
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

def extract_frame_for_clip(
    video_path: Path,
    timestamp_s: float,
    target_size: tuple[int, int] = (224, 224),
) -> np.ndarray | None:
    """
    Extract a single frame from video at timestamp, downsampled to target_size.
    Gap 256 Fix: Uses FFmpeg to resize *before* loading into memory to avoid 4K OOM.
    """
    if not video_path.exists():
        logger.error("Video file not found: %s", video_path)
        return None

    w, h = target_size
    # FFmpeg command to seek to timestamp and extract 1 frame, resized
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp_s),
        "-i", str(video_path),
        "-frames:v", "1",
        "-f", "image2pipe",
        "-pix_fmt", "rgb24",
        "-vcodec", "rawvideo",
        "-s", f"{w}x{h}",  # Downsample at the FFmpeg level
        "-"
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

        if result.returncode != 0:
            logger.error("FFmpeg frame extraction failed: %s", result.stderr.decode(errors="replace"))
            return None

        expected_size = w * h * 3
        if len(result.stdout) != expected_size:
            logger.error(
                "Unexpected FFmpeg frame size for %s at %.2fs: got %d bytes, expected %d",
                video_path.name,
                timestamp_s,
                len(result.stdout),
                expected_size,
            )
            return None

        # Convert raw bytes to numpy array only after validating byte count.
        frame = np.frombuffer(result.stdout, dtype=np.uint8).reshape((h, w, 3))
        return frame

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg frame extraction timed out for %s at %.2fs", video_path.name, timestamp_s)
        return None
    except Exception as e:
        logger.exception("Error extracting frame from %s: %s", video_path, e)
        return None

def batch_extract_frames(
    video_path: Path,
    timestamps: list[float],
    target_size: tuple[int, int] = (224, 224),
) -> list[np.ndarray]:
    """Extract multiple frames efficiently."""
    frames = []
    for ts in timestamps:
        frame = extract_frame_for_clip(video_path, ts, target_size)
        if frame is not None:
            frames.append(frame)
    return frames
