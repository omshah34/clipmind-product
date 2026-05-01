import subprocess
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PLATFORM_SPECS = {
    "instagram_reels": {"aspect": (9, 16), "max_duration": 90,  "max_size_mb": 100},
    "tiktok":          {"aspect": (9, 16), "max_duration": 600, "max_size_mb": 500},
    "youtube_shorts":  {"aspect": (9, 16), "max_duration": 60,  "max_size_mb": 256},
    "linkedin":        {"aspect": (16, 9), "max_duration": 600, "max_size_mb": 200, "max_bitrate_kbps": 30_000},
    "youtube":         {"aspect": (16, 9), "max_duration": None, "max_size_mb": 128_000},
}

PLATFORM_AUDIO_TARGETS = {
    "tiktok":          192,   # kbps — TikTok can handle 192k AAC
    "instagram_reels": 192,
    "youtube_shorts":  192,
    "youtube":         256,
    "linkedin":        128,
}

def get_video_metadata(path: str) -> dict:
    """Run ffprobe to get video streams and format information."""
    result = subprocess.run([
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_streams", "-show_format", path
    ], capture_output=True, text=True, check=True)
    try:
        # json.loads raises only json.JSONDecodeError — not KeyError
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error(f"Failed to parse ffprobe output: {result.stdout}")
        raise

def get_source_audio_bitrate(video_path: str) -> int:
    """Gap 329: Returns audio bitrate in kbps from source file."""
    try:
        result = subprocess.run([
            "ffprobe", "-v", "quiet", "-select_streams", "a:0",
            "-show_entries", "stream=bit_rate",
            "-of", "json", video_path
        ], capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [{}])
        if streams and "bit_rate" in streams[0]:
            return int(streams[0]["bit_rate"]) // 1000
        return 128
    except Exception as e:
        logger.warning(f"Failed to probe source audio bitrate: {e}")
        return 128

def get_adaptive_audio_bitrate(video_path: str, platform: str) -> int:
    """
    Gap 329: Use source bitrate if it's lower than platform target.
    Never upsample — that wastes bytes without quality gain.
    """
    source_kbps = get_source_audio_bitrate(video_path)
    target_kbps = PLATFORM_AUDIO_TARGETS.get(platform, 128)

    # Don't upsample — take the lower of source vs target
    chosen = min(source_kbps, target_kbps)
    # But never go below 96kbps
    return max(chosen, 96)

def prepare_for_platform(input_path: str, output_path: str, platform: str) -> None:
    """
    Gap 283: Transcode clip to meet exact platform specs.
    Handles aspect ratio reframing, scaling, and bitrate caps.
    """
    if platform not in PLATFORM_SPECS:
        logger.warning(f"No specs for platform: {platform}. Copying input.")
        subprocess.run(["ffmpeg", "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return

    spec = PLATFORM_SPECS[platform]
    meta = get_video_metadata(input_path)
    video_stream = next(s for s in meta["streams"] if s["codec_type"] == "video")

    w, h = int(video_stream["width"]), int(video_stream["height"])
    target_w, target_h = spec["aspect"]

    # Build filter chain
    filters = []

    # Reframe to target aspect ratio
    current_ratio = w / h
    target_ratio = target_w / target_h
    if abs(current_ratio - target_ratio) > 0.01:
        if current_ratio > target_ratio:
            # Too wide — crop sides
            new_w = int(h * target_ratio)
            filters.append(f"crop={new_w}:{h}:(iw-{new_w})/2:0")
        else:
            # Too tall — crop top/bottom
            new_h = int(w / target_ratio)
            filters.append(f"crop={w}:{new_h}:0:(ih-{new_h})/2")

    # Scale to platform-safe resolution
    # Standardize on 1080p for vertical, 1920p for horizontal
    if spec["aspect"] == (9, 16):
        filters.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2")
    else:
        filters.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2")
    
    filters.append("format=yuv420p")

    vf = ",".join(filters)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf]

    # Gap 287: LinkedIn bitrate cap
    if "max_bitrate_kbps" in spec:
        cmd += ["-b:v", f"{spec['max_bitrate_kbps']}k", "-maxrate", f"{spec['max_bitrate_kbps']}k", "-bufsize", f"{spec['max_bitrate_kbps'] * 2}k"]

    # Gap 329: Adaptive audio bitrate
    audio_kbps = get_adaptive_audio_bitrate(input_path, platform)
    cmd += ["-c:v", "libx264", "-preset", "fast", "-c:a", "aac", "-b:a", f"{audio_kbps}k", output_path]
    subprocess.run(cmd, check=True)

def validate_for_linkedin(video_path: str) -> None:
    """
    Gap 287: LinkedIn-specific pre-upload validation.
    """
    meta = get_video_metadata(video_path)
    fmt = meta["format"]
    size_mb = float(fmt["size"]) / 1_048_576
    duration = float(fmt["duration"])
    bitrate_kbps = float(fmt.get("bit_rate", 0)) / 1000

    errors = []
    if size_mb > 200:
        errors.append(f"File too large: {size_mb:.0f}MB > 200MB LinkedIn limit")
    if duration > 600:
        errors.append(f"Too long: {duration:.0f}s > 600s LinkedIn limit")
    if bitrate_kbps > 30_000:
        errors.append(f"Bitrate too high: {bitrate_kbps:.0f}kbps > 30,000kbps")

    if errors:
        raise ValueError("LinkedIn validation failed:\n" + "\n".join(errors))
