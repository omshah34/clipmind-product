"""File: services/instagram_publisher.py
Purpose: Uploads video clips to Instagram Reels via the Instagram Graph API.
         Uses a two-step process: initiate container, then poll via Celery retries (non-blocking).
"""
import requests
import logging

logger = logging.getLogger(__name__)


def create_instagram_container(video_url: str, caption: str, hashtags: list[str], access_token: str, instagram_account_id: str) -> str:
    """Step 1: Create a media container and return its container_id.
    
    The container is NOT yet published — call poll_and_publish_container() after this.
    """
    full_caption = caption
    if hashtags:
        full_caption += "\n\n" + " ".join([f"#{t}" for t in hashtags])

    container_url = f"https://graph.facebook.com/v19.0/{instagram_account_id}/media"
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": full_caption[:2200],  # IG caption limit
        "access_token": access_token
    }

    logger.info(f"Initiating Instagram Reel container creation for account {instagram_account_id}...")
    container_res = requests.post(container_url, data=payload, timeout=30)

    if not container_res.ok:
        logger.error(f"IG Container Error: {container_res.text}")
        container_res.raise_for_status()

    container_id = container_res.json().get("id")
    if not container_id:
        raise Exception(f"Instagram returned no container ID: {container_res.json()}")

    logger.info(f"Instagram container {container_id} created. Awaiting processing...")
    return container_id


def check_container_status(container_id: str, access_token: str) -> str:
    """Returns the container status_code: FINISHED, IN_PROGRESS, or ERROR."""
    status_url = f"https://graph.facebook.com/v19.0/{container_id}"
    params = {"fields": "status_code", "access_token": access_token}
    status_res = requests.get(status_url, params=params, timeout=15)
    status_res.raise_for_status()
    return status_res.json().get("status_code", "UNKNOWN")


def publish_container(container_id: str, instagram_account_id: str, access_token: str) -> str:
    """Step 2: Publish a FINISHED container to the Instagram feed. Returns publish_id."""
    publish_url = f"https://graph.facebook.com/v19.0/{instagram_account_id}/media_publish"
    publish_payload = {"creation_id": container_id, "access_token": access_token}

    logger.info(f"Publishing Instagram container {container_id}...")
    publish_res = requests.post(publish_url, data=publish_payload, timeout=30)

    if not publish_res.ok:
        logger.error(f"IG Publish Error: {publish_res.text}")
        publish_res.raise_for_status()

    publish_id = publish_res.json().get("id")
    if not publish_id:
        raise Exception(f"Instagram returned no publish ID: {publish_res.json()}")

    logger.info(f"Instagram published successfully with ID: {publish_id}")
    return str(publish_id)


def upload_to_instagram(video_url: str, caption: str, hashtags: list[str], access_token: str, instagram_account_id: str) -> str:
    """
    Legacy synchronous wrapper — kept for backward compatibility.
    WARNING: Prefer the split create_instagram_container + Celery retry approach
    in high-throughput scenarios to avoid blocking workers.
    """
    container_id = create_instagram_container(video_url, caption, hashtags, access_token, instagram_account_id)

    # Non-blocking: dispatch to Celery for async status polling
    from workers.publish_social import poll_instagram_container
    poll_instagram_container.apply_async(
        kwargs={
            "container_id": container_id,
            "instagram_account_id": instagram_account_id,
            "access_token": access_token,
        },
        countdown=15,  # Wait 15s before first check
    )
    # Return the container_id as a placeholder — real publish_id comes from the Celery task
    return f"ig_pending_{container_id}"

    
    # Format caption
    full_caption = caption
    if hashtags:
        full_caption += "\n\n" + " ".join([f"#{t}" for t in hashtags])
        
    # Step 1: Create a media container (initiate upload)
    container_url = f"https://graph.facebook.com/v19.0/{instagram_account_id}/media"
    
    payload = {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": full_caption[:2200],  # IG caption limit
        "access_token": access_token
    }
    
    logger.info(f"Initiating Instagram Reel container creation for account {instagram_account_id}...")
    container_res = requests.post(container_url, data=payload)
    
    if not container_res.ok:
        logger.error(f"IG Container Error: {container_res.text}")
        container_res.raise_for_status()
        
    container_id = container_res.json().get("id")
    
    # Step 2: Poll for media container status to be FINISHED
    status_url = f"https://graph.facebook.com/v19.0/{container_id}"
    params = {
        "fields": "status_code",
        "access_token": access_token
    }
    
    max_attempts = 10
    success = False
    
    for attempt in range(max_attempts):
        logger.info(f"Polling Instagram container status (attempt {attempt+1})...")
        time.sleep(10)  # Wait for IG to fetch and process the video URL
        status_res = requests.get(status_url, params=params)
        
        if status_res.ok:
            status_data = status_res.json()
            status_code = status_data.get("status_code")
            logger.info(f"Instagram Container Status: {status_code}")
            
            if status_code == "FINISHED":
                success = True
                break
            elif status_code == "ERROR":
                raise Exception("Instagram container processing failed.")
    
    if not success:
        raise Exception("Instagram container processing timed out.")
    
    # Step 3: Publish the media container
    publish_url = f"https://graph.facebook.com/v19.0/{instagram_account_id}/media_publish"
    publish_payload = {
        "creation_id": container_id,
        "access_token": access_token
    }
    
    logger.info("Publishing Instagram Reel container to feed...")
    publish_res = requests.post(publish_url, data=publish_payload)
    
    if not publish_res.ok:
        logger.error(f"IG Publish Error: {publish_res.text}")
        publish_res.raise_for_status()
        
    publish_id = publish_res.json().get("id")
    logger.info(f"Instagram published successfully with ID: {publish_id}")
    
    return str(publish_id)
