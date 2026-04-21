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
    """Download a video from YouTube to the specified path."""
    if not validate_url(url):
        raise VideoDownloaderError("Domain not allowed.")

    # We want a single file, preferably mp4, with decent quality but not 4K (save bandwidth)
    ydl_opts = {
        'format': 'bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': str(output_path),
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
    }

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
    except Exception as e:
        logger.error("Failed to download video: %s", e)
        raise VideoDownloaderError(f"Download failed: {str(e)}")
