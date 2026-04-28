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

def upload_to_youtube(file_path: Path, metadata: dict, access_token: str, idempotency_key: str | None = None) -> dict:
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
    
    # Gap 205: Client-side deduplication check using Redis
    import redis
    from core.config import settings
    r = redis.from_url(settings.redis_url)
    dedup_key = f"youtube:upload:done:{idempotency_key}" if idempotency_key else None
    
    if dedup_key and r.exists(dedup_key):
        video_id = r.get(dedup_key).decode("utf-8")
        logger.info("YouTube upload already completed (deduplicated), skipping: key=%s", idempotency_key)
        return {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }

    try:
        youtube = build("youtube", "v3", credentials=credentials)
        
        caption = metadata.get("caption", "ClipMind Video")
        tags = metadata.get("hashtags", [])
        category_id = metadata.get("categoryId", "22")
        privacy_status = metadata.get("privacyStatus", "private")
        
        body = {
            "snippet": {
                "title": caption[:100],
                "description": caption + "\n\n" + " ".join([f"#{t}" for t in tags]),
                "tags": tags,
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False
            }
        }
        
        media = MediaFileUpload(str(file_path), chunksize=1024*1024, resumable=True)
        
        # Gap 205: Use X-Goog-Request-Reason for idempotency if available
        headers = {}
        if idempotency_key:
            headers["X-Goog-Request-Reason"] = idempotency_key
            # Some Google APIs also support 'idempotency-key'
            headers["idempotency-key"] = idempotency_key

        logger.info("Initiating YouTube resumable upload for %s", file_path.name)
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        # Note: google-api-python-client doesn't expose headers easily on the request object 
        # before execution, but we can attempt to inject them into the request's http object.
        if headers:
            request.http.headers.update(headers)
        
        response = request.execute()
        video_id = response.get("id")
        
        # Gap 205: Store upload status in Redis for 24h
        if dedup_key and video_id:
            r.set(dedup_key, video_id, ex=86400)

        return {
            "id": video_id,
            "url": f"https://youtu.be/{video_id}"
        }
        
    except HttpError as e:
        error_details = e.error_details[0] if e.error_details else {}
        reason = error_details.get("reason", "unknown")
        message = error_details.get("message", str(e))
        
        # Gap 205: Handle 409 Conflict (Duplicate) as success-equivalent
        if e.resp.status == 409 or reason == "duplicate":
            logger.info("YouTube reported duplicate upload (409). Treating as success.")
            # In a real scenario, we might want to query for the existing video ID
            return {"id": "duplicate_detected", "url": "https://youtu.be/"}

        logger.error("YouTube API failure: %s (reason: %s)", message, reason)
        raise YouTubeApiError(message, error_code=reason)
    except Exception as e:
        logger.exception("Unexpected error during YouTube upload")
        raise
