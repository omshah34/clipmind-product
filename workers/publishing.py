import asyncio
import httpx
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

async def upload_youtube_short(
    token: str,
    video_path: str,
    thumbnail_path: str | None,
    title: str,
    description: str,
) -> str:
    """
    Gap 285: Upload video, wait for YouTube processing, then inject thumbnail.
    YouTube requires the video to be fully processed before a custom thumbnail can be set.
    """

    # Step 1: Upload video
    video_id = await _upload_video_to_youtube(token, video_path, title, description)
    logger.info(f"Video uploaded to YouTube: {video_id}")

    # Step 2: Wait for YouTube to finish processing (required before thumbnail)
    try:
        await _wait_for_youtube_processing(token, video_id, timeout=300)
        logger.info(f"YouTube video {video_id} processed successfully.")
    except Exception as e:
        logger.warning(f"Waiting for YouTube processing failed or timed out: {e}")
        # We still return the video_id even if thumbnail fails
        return video_id

    # Step 3: Inject thumbnail (separate API call)
    if thumbnail_path and Path(thumbnail_path).exists():
        try:
            await _set_youtube_thumbnail(token, video_id, thumbnail_path)
            logger.info(f"Thumbnail set for video: {video_id}")
        except Exception as e:
            logger.error(f"Failed to set YouTube thumbnail for {video_id}: {e}")

    return video_id

async def _upload_video_to_youtube(token: str, video_path: str, title: str, description: str) -> str:
    """Mock/Simplified YouTube video upload (Placeholder for real Google API client logic)."""
    # In a real implementation, we'd use the Resumable Upload protocol or Google API client
    # For now, we simulate the return of a video_id
    await asyncio.sleep(2)
    return "yt_video_id_placeholder"

async def _wait_for_youtube_processing(token: str, video_id: str, timeout: int) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    async with httpx.AsyncClient() as client:
        while asyncio.get_event_loop().time() < deadline:
            resp = await client.get(
                f"https://www.googleapis.com/youtube/v3/videos?part=status&id={video_id}",
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code != 200:
                # If we get a 404/403, we might need to wait longer if it's just propagation
                await asyncio.sleep(10)
                continue
                
            items = resp.json().get("items", [])
            if not items:
                await asyncio.sleep(10)
                continue
                
            status = items[0]["status"]["uploadStatus"]
            if status == "processed":
                return
            if status == "failed":
                raise RuntimeError(f"YouTube processing failed for {video_id}")
            
            await asyncio.sleep(15)
    raise TimeoutError(f"YouTube video {video_id} did not process within {timeout}s")

async def _set_youtube_thumbnail(token: str, video_id: str, thumbnail_path: str) -> None:
    with open(thumbnail_path, "rb") as f:
        data = f.read()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={video_id}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "image/jpeg"},
            content=data,
        )
    resp.raise_for_status()
