import logging
import subprocess

logger = logging.getLogger(__name__)

TIKTOK_SAFE_ZONES = {
    # TikTok UI overlays these regions — avoid placing watermarks here
    "top":    (0.0, 0.0, 1.0, 0.08),   # progress bar
    "bottom": (0.0, 0.80, 1.0, 1.0),   # CTA buttons + username
    "right":  (0.85, 0.0, 1.0, 1.0),   # action buttons sidebar
}

def validate_watermark_position(
    x_pct: float,  # 0.0–1.0 (left edge of watermark)
    y_pct: float,  # 0.0–1.0 (top edge of watermark)
    w_pct: float,  # watermark width as fraction of video width
    h_pct: float,  # watermark height as fraction of video height
    platform: str = "tiktok",
) -> None:
    """
    Gap 290: TikTok Watermark Bounds Check.
    Ensures watermarks aren't obscured by platform-native UI overlays.
    """
    if platform != "tiktok":
        return

    wm_rect = (x_pct, y_pct, x_pct + w_pct, y_pct + h_pct)

    for zone_name, zone_rect in TIKTOK_SAFE_ZONES.items():
        if _rects_overlap(wm_rect, zone_rect):
            raise ValueError(
                f"Watermark overlaps TikTok's '{zone_name}' UI zone. "
                f"Move watermark away from: {zone_rect}"
            )

def _rects_overlap(r1: tuple, r2: tuple) -> bool:
    """Returns True if two (x1,y1,x2,y2) rects overlap."""
    return not (r1[2] <= r2[0] or r1[0] >= r2[2] or
                r1[3] <= r2[1] or r1[1] >= r2[3])


MAX_WATERMARK_PX = 512  # Scale down to this before overlay — never full 4K

def prepare_watermark(watermark_path: str, video_width: int, video_height: int) -> str:
    """
    Gap 328: Scale watermark to at most MAX_WATERMARK_PX while preserving alpha.
    Returns path to the downscaled temp watermark.
    """
    import tempfile, os
    # Use a persistent temp file name for the duration of the render
    fd, out_path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    target_size = min(MAX_WATERMARK_PX, int(video_width * 0.2))  # Max 20% of video width

    subprocess.run([
        "ffmpeg", "-y", "-i", watermark_path,
        "-vf", f"scale={target_size}:-1:flags=lanczos",  # High-quality downscale
        "-pix_fmt", "rgba",   # Preserve alpha channel
        out_path
    ], check=True, capture_output=True)

    return out_path

def build_watermark_filter(
    watermark_path: str,
    video_width: int,
    video_height: int,
    position: str = "bottom_right",
    opacity: float = 0.8,
) -> tuple[str, str]:
    """Gap 328: Returns (input_flag, filtergraph) for FFmpeg watermark overlay."""
    scaled_wm = prepare_watermark(watermark_path, video_width, video_height)

    POSITIONS = {
        "top_left":     "10:10",
        "top_right":    "W-w-10:10",
        "bottom_left":  "10:H-h-10",
        "bottom_right": "W-w-10:H-h-10",
        "center":       "(W-w)/2:(H-h)/2",
    }
    pos = POSITIONS.get(position, POSITIONS["bottom_right"])
    
    # Overlay filter with alpha straight to prevent artifacts
    overlay = f"[wm]overlay={pos}:format=auto:alpha=straight"
    filtergraph = f"[1:v]format=rgba,colorchannelmixer=aa={opacity}[wm];[0:v]{overlay}"

    return scaled_wm, filtergraph
