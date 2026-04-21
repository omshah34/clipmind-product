"""File: services/source_ingestion.py
Purpose: Handles automated fetching of content from external sources (YouTube, RSS).
         Detects new videos and triggers processing jobs.
"""

from __future__ import annotations

import logging
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from db.repositories.source_ingestion import (
    update_source_status,
    record_ingestion_atomic,
    is_video_processed,
)
from services.task_queue import dispatch_task
from services.event_emitter import emit_event

logger = logging.getLogger(__name__)

class SourceIngestionService:
    def __init__(self) -> None:
        pass

    def poll_source(self, source: dict[str, Any]) -> int:
        """Poll a source for new content and return number of new jobs created."""
        source_id = source["id"]
        source_type = source["source_type"]
        user_id = source["user_id"]
        config = source["config_json"]
        
        logger.info("[Autopilot] [source=%s] Polling started (%s)", source_id, source_type)
        
        try:
            video_entries = [] # List of {"id": str, "url": str}
            
            if source_type == "youtube_channel":
                video_entries = self._poll_youtube(config)
            elif source_type == "tiktok_channel":
                video_entries = self._poll_tiktok(config)
            elif source_type == "rss_feed":
                video_entries = self._poll_rss(config)
            else:
                logger.warning("[source=%s] Unknown source type: %s", source_id, source_type)
                update_source_status(source_id, last_error=f"Unknown source type: {source_type}")
                return 0

            jobs_created = 0
            for entry in video_entries:
                vid = entry["id"]
                vurl = entry["url"]
                
                # Deduplication Check
                if is_video_processed(source_id, vid):
                    logger.debug("[source=%s] Video %s already processed. Skipping.", source_id, vid)
                    continue
                
                logger.info("[source=%s] New video found: %s. Creating job...", source_id, vid)
                
                # Transactional Ingestion
                # Note: We use a default 'v4' prompt for Autopilot
                new_job_id = record_ingestion_atomic(
                    source_id=source_id,
                    user_id=user_id,
                    video_id=vid,
                    video_url=vurl
                )
                
                # Dispatch to AI Pipeline
                dispatch_task(
                    "workers.pipeline.process_job",
                    job_id=new_job_id
                )
                
                # Notify User
                emit_event(
                    "source.video_ingested",
                    {
                        "source_id": source_id,
                        "video_id": vid,
                        "job_id": new_job_id,
                        "url": vurl
                    },
                    user_id=user_id
                )
                
                jobs_created += 1

            update_source_status(source_id, success=True)
            return jobs_created

        except Exception as exc:
            error_msg = f"Polling failed: {str(exc)}"
            logger.error("[source=%s] %s", source_id, error_msg, exc_info=True)
            update_source_status(source_id, last_error=error_msg)
            return 0

    def _poll_youtube(self, config: dict) -> list[dict[str, str]]:
        """Use yt-dlp to get the latest 3 video IDs from a channel."""
        channel_url = config.get("channel_url")
        if not channel_url:
            return []

        try:
            # metadata-only lookup for 3 most recent
            cmd = [
                "yt-dlp",
                "--get-id",
                "--playlist-items", "1:3",
                "--flat-playlist",
                channel_url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            video_ids = [vid.strip() for vid in result.stdout.split("\n") if vid.strip()]
            
            return [
                {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
                for vid in video_ids
            ]
        except Exception as exc:
            logger.error("yt-dlp failed to poll YouTube channel %s: %s", channel_url, exc)
            raise
        
        return []

    def _poll_tiktok(self, config: dict) -> list[dict[str, str]]:
        """Use yt-dlp to get latest 3 videos from TikTok (Experimental)."""
        channel_url = config.get("channel_url")
        if not channel_url:
            return []

        try:
            cmd = [
                "yt-dlp",
                "--get-id",
                "--playlist-items", "1:3",
                "--flat-playlist",
                channel_url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            video_ids = [vid.strip() for vid in result.stdout.split("\n") if vid.strip()]
            
            return [
                {"id": vid, "url": f"https://www.tiktok.com/@user/video/{vid}"}
                for vid in video_ids
            ]
        except Exception as exc:
            logger.error("yt-dlp failed to poll TikTok channel %s: %s", channel_url, exc)
            raise 
            
        return []

    def _poll_rss(self, config: dict) -> list[dict[str, str]]:
        """Stub for RSS polling."""
        return []

def get_source_ingestion_service() -> SourceIngestionService:
    return SourceIngestionService()
