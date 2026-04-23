"""File: services/video_downloader.py
Purpose: Handles server-side downloading of videos from YouTube using yt-dlp.
         Provides metadata extraction and secure downloading to temp directories.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

from core.config import settings

try:
    import yt_dlp
except ModuleNotFoundError:  # pragma: no cover - optional dependency guard
    yt_dlp = None

logger = logging.getLogger(__name__)

# Security: Only allow YouTube/Shorts domains
ALLOWED_DOMAINS = [
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
    "m.youtube.com"
]

# Gap 94: Max resolution cap — 1080p is sufficient for vertical clip generation
# and avoids unnecessary 4K bandwidth/storage costs
_MAX_HEIGHT = int(os.getenv("YTDLP_MAX_HEIGHT", "1080"))

class VideoDownloaderError(Exception):
    """Base exception for video downloader service."""
    pass


def _require_yt_dlp() -> Any:
    """Return the yt-dlp module or raise a clear service error."""
    if yt_dlp is None:
        raise VideoDownloaderError(
            "yt-dlp is not installed. Add it to requirements and reinstall dependencies."
        )
    return yt_dlp

def validate_url(url: str) -> bool:
    """Check if the URL belongs to an allowed domain."""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    return any(domain == d for d in ALLOWED_DOMAINS)

def get_video_info(url: str) -> dict[str, Any]:
    """Extract metadata from a YouTube URL without downloading."""
    if not validate_url(url):
        raise VideoDownloaderError("Domain not allowed. Only YouTube links are supported.")

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }

    try:
        ytdlp = _require_yt_dlp()
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error("Failed to extract video info: %s", e)
        raise VideoDownloaderError(f"Could not fetch video info: {str(e)}")

def download_video(url: str, output_path: Path) -> Path:
    """Download a video from YouTube to the specified path.

    Gap 96: Raises VideoDownloaderError immediately if the URL is a live stream
    to prevent the worker from hanging indefinitely.
    Gap 94: Resolution capped at _MAX_HEIGHT (default 1080p) to avoid 4K storage waste.
    """
    if not validate_url(url):
        raise VideoDownloaderError("Domain not allowed.")

    # Gap 96: Pre-flight live stream detection — avoids indefinite hang
    try:
        info = get_video_info(url)
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            raise VideoDownloaderError(
                "Live streams and upcoming broadcasts cannot be processed. "
                "Please wait until the stream has ended and the VOD is available."
            )
    except VideoDownloaderError:
        raise
    except Exception as e:
        logger.warning("Live-stream pre-check failed (continuing anyway): %s", e)

    # Gap 94: Quality capped at _MAX_HEIGHT to save bandwidth and storage
    ydl_opts = {
        'format': f'bestvideo[ext=mp4][height<={_MAX_HEIGHT}]+bestaudio[ext=m4a]/best[ext=mp4][height<={_MAX_HEIGHT}]/best[height<={_MAX_HEIGHT}]/best',
        'outtmpl': str(output_path),
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

    # Gap 92: Support authenticated downloads for age-restricted/private videos
    if settings.ytdlp_cookies_file:
        cookie_path = Path(settings.ytdlp_cookies_file)
        if cookie_path.exists():
            ydl_opts['cookiefile'] = str(cookie_path)
            logger.info("Using yt-dlp cookies from: %s", cookie_path)
        else:
            logger.warning("YTDLP_COOKIES_FILE configured but not found: %s", cookie_path)

    try:
        ytdlp = _require_yt_dlp()
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if not output_path.exists():
            # yt-dlp might append .mp4 if not present in template or if it merged
            actual_path = output_path.with_suffix('.mp4')
            if actual_path.exists():
                actual_path.rename(output_path)
            else:
                raise VideoDownloaderError("Download finished but output file was not found.")
        
        return output_path
    except VideoDownloaderError:
        raise
    except Exception as e:
        logger.error("Failed to download video: %s", e)
        raise VideoDownloaderError(f"Download failed: {str(e)}")
