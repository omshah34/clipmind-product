"""File: services/youtube_publisher.py
Purpose: Uploads video clips to YouTube via the YouTube Data API v3 (Resumable Upload).
"""
import os
import logging
from pathlib import Path

try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from googleapiclient.errors import HttpError
    HAS_GOOGLE_API = True
except ImportError:
    HAS_GOOGLE_API = False

logger = logging.getLogger(__name__)

class YouTubeApiError(Exception):
    """Custom exception for YouTube API specific errors."""
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code

def upload_to_youtube(file_path: Path, metadata: dict, access_token: str) -> dict:
    """Uploads a local video to YouTube using the YouTube Data API v3.
    
    Args:
        file_path: Path to the local .mp4 file.
        metadata: Dictionary with 'caption' and optional 'hashtags'.
        access_token: Validated/refreshed access token.
        
    Returns:
        dict: {'id': video_id, 'url': video_url}
    """
    if not HAS_GOOGLE_API:
        raise ImportError("google-api-python-client is not installed.")
        
    if not file_path.exists():
        raise FileNotFoundError(f"Video file not found: {file_path}")

    # Build Credentials object (access token only, as worker handles refresh)
    credentials = Credentials(token=access_token)
    
    try:
        youtube = build("youtube", "v3", credentials=credentials)
        
        caption = metadata.get("caption", "ClipMind Video")
        tags = metadata.get("hashtags", [])
        
        body = {
            "snippet": {
                "title": caption[:100],
                "description": caption + "\n\n" + " ".join([f"#{t}" for t in tags]),
                "tags": tags,
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False
            }
        }
        
        media = MediaFileUpload(str(file_path), chunksize=1024*1024, resumable=True)
        
        logger.info("Initiating YouTube resumable upload for %s", file_path.name)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = request.execute()
        video_id = response.get("id")
        return {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }
        
    except HttpError as e:
        error_details = e.error_details[0] if e.error_details else {}
        reason = error_details.get("reason", "unknown")
        message = error_details.get("message", str(e))
        
        logger.error("YouTube API failure: %s (reason: %s)", message, reason)
        raise YouTubeApiError(message, error_code=reason)
    except Exception as e:
        logger.exception("Unexpected error during YouTube upload")
        raise
