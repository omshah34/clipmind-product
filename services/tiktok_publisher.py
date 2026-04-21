"""File: services/tiktok_publisher.py
Purpose: Uploads video clips to TikTok via the TikTok Content Posting API (Direct Video Upload).
"""
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class TikTokApiError(Exception):
    """Custom exception for TikTok API specific errors."""
    def __init__(self, message: str, error_code: str | None = None):
        super().__init__(message)
        self.error_code = error_code

def upload_to_tiktok(file_path: Path, metadata: dict, access_token: str, open_id: str) -> dict:
    """Uploads a local video to TikTok using the 3-phase Direct Video Upload flow.
    
    Args:
        file_path: Path to local .mp4 file.
        metadata: Dict with 'caption' and 'hashtags'.
        access_token: Refreshed TikTok access token.
        open_id: User's OpenID.
        
    Returns:
        dict: {'id': publish_id, 'url': ...}
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Video file not found: {file_path}")

    # 1. Initialize Upload
    # TikTok API v2 init endpoint
    init_url = "https://open.tiktokapis.com/v2/post/publish/video/init/"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    caption = metadata.get("caption", "ClipMind Video")
    tags = metadata.get("hashtags", [])
    full_text = caption + " " + " ".join([f"#{t}" for t in tags])
    
    payload = {
        "post_info": {
            "title": full_text[:150],
            "privacy_level": "PRIVATE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": file_path.stat().st_size,
            "chunk_size": file_path.stat().st_size, # For now, single chunk
            "total_chunk_count": 1
        }
    }
    
    logger.info("Initiating TikTok direct upload for %s (%d bytes)", file_path.name, payload["source_info"]["video_size"])
    response = requests.post(init_url, json=payload, headers=headers)
    
    if not response.ok:
        logger.error("TikTok Init failed: %s", response.text)
        raise TikTokApiError(f"TikTok Init failed: {response.text}", error_code="init_failed")
        
    data = response.json()
    if data.get("error", {}).get("code") != "ok":
        raise TikTokApiError(data["error"]["message"], error_code=data["error"]["code"])
        
    upload_url = data["data"]["upload_url"]
    publish_id = data["data"]["publish_id"]
    
    # 2. Upload Video (Single Chunk)
    logger.info("Uploading video chunk to TikTok...")
    with open(file_path, "rb") as f:
        file_data = f.read()
        
    upload_headers = {
        "Content-Type": "video/mp4",
        "Content-Range": f"bytes 0-{len(file_data)-1}/{len(file_data)}"
    }
    
    # TikTok uses PUT for the actual media upload
    put_response = requests.put(upload_url, data=file_data, headers=upload_headers)
    if not put_response.ok:
        logger.error("TikTok Media Upload failed: %s", put_response.text)
        raise TikTokApiError(f"Media Upload failed: {put_response.text}", error_code="upload_failed")
        
    logger.info("TikTok publish initiated with ID: %s", publish_id)
    return {
        "id": publish_id,
        "url": "https://www.tiktok.com/" # TikTok doesn't provide a public URL immediately
    }
