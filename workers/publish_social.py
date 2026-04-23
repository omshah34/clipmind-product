"""File: workers/publish_social.py
Purpose: Social media publishing worker using secure JIT token refreshes.
"""
import logging
import os
from pathlib import Path
from uuid import UUID

import httpx
from openai import APIConnectionError, APITimeoutError, RateLimitError
from workers.celery_app import celery_app
from services.token_manager import TokenManager
from services.youtube_publisher import upload_to_youtube, YouTubeApiError
from services.tiktok_publisher import upload_to_tiktok, TikTokApiError

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (httpx.TimeoutException, APIConnectionError, APITimeoutError, RateLimitError)


# Standardized return schema for all platforms
def make_response(status="failed", platform_id=None, url=None, error=None, error_code=None):
    return {
        "status": status,
        "platform_id": platform_id,
        "url": url,
        "error": error,
        "error_code": error_code
    }

@celery_app.task(bind=True, max_retries=4)
def publish_to_platform(
    self,
    user_id: str | UUID,
    job_id: str | UUID,
    clip_index: int,
    platform: str,
    social_account_id: str | UUID,
    caption: str,
    hashtags: list[str] | None = None,
    publish_queue_id: str | None = None,
):
    """Securely publish a clip to a social platform with JIT token refresh.
    
    Returns a standardized dictionary for frontend consumption.
    """
    logger.info("Starting publish task for user %s, job %s, platform %s", user_id, job_id, platform)
    
    # 1. Fetch Token (Just-In-Time Refresh)
    # TokenManager handles encryption/decryption and expiration internally
    token_data = TokenManager.get_valid_token(user_id, platform)
    
    if not token_data:
        logger.error("No valid %s token found for user %s", platform, user_id)
        return make_response(error="Token unavailable or expired", error_code="token_unavailable")

    # 2. Locate local file
    # For now, we assume clips are stored in a predictable local path
    # In a real system, we'd fetch the URL and download to temp, or use shared storage
    clip_filename = f"{job_id}_clip_{clip_index}.mp4"
    file_path = Path(os.getenv("STORAGE_PATH", "exports")) / clip_filename
    
    if not file_path.exists():
        logger.error("Clip file not found: %s", file_path)
        return make_response(error="Local file not found", error_code="file_not_found")
    metadata = {
        "caption": caption,
        "hashtags": hashtags or [],
    }

    try:
        # 3. Platform Specific Logic
        if platform.lower() == "youtube":
            # YouTube v2 (Resumable Upload)
            # TokenManager returns a single access_token string for YouTube
            access_token = token_data
            result = upload_to_youtube(file_path, metadata, access_token)
            return make_response("published", result["id"], result["url"])

        elif platform.lower() == "tiktok":
            # TikTok v2 (Direct Video Upload)
            # TokenManager returns a tuple (access_token, open_id) for TikTok
            access_token, open_id = token_data
            result = upload_to_tiktok(file_path, metadata, access_token, open_id)
            return make_response("published", result["id"], result["url"])

        else:
            return make_response(error=f"Unsupported platform: {platform}", error_code="unsupported_platform")

    except YouTubeApiError as e:
        if e.error_code == "quotaExceeded":
            return make_response(error="Daily YouTube quota exceeded", error_code="youtube_quota_exceeded")
        elif e.error_code in ["invalid_grant", "unauthorized"]:
            return make_response(error="YouTube session expired", error_code="youtube_auth_expired")
        else:
            return make_response(error=str(e), error_code="youtube_api_error")

    except TikTokApiError as e:
        # Gap 110: Handle TikTok specific error codes for better UX
        if e.error_code == "spam_risk_too_many_requests":
            # Use standardized exponential backoff for transient spam risks
            countdown = 2 ** self.request.retries * 60
            raise self.retry(exc=e, countdown=countdown)
        elif e.error_code == "video_too_short":
            return make_response(error="TikTok requires videos to be at least 3 seconds long.", error_code="tiktok_video_too_short")
        elif e.error_code == "permission_denied":
            return make_response(error="TikTok permission denied. Please reconnect your account.", error_code="tiktok_permission_denied")
        elif e.error_code == "account_banned":
            return make_response(error="Your TikTok account appears to be restricted or banned.", error_code="tiktok_account_restricted")
        
        return make_response(error=str(e), error_code=f"tiktok_{e.error_code or 'api_error'}")

    except TRANSIENT_ERRORS as exc:
        logger.warning(f"Transient network error during %s publishing: %s", platform, exc)
        countdown = 2 ** self.request.retries * 60
        raise self.retry(exc=exc, countdown=countdown)

    except Exception as e:
        logger.exception("Unexpected error during %s publishing", platform)
        return make_response(error=str(e), error_code="internal_error")
