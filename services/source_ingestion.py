"""File: services/source_ingestion.py
Purpose: Handles automated fetching of content from external sources (YouTube, RSS).
         Detects new videos and triggers processing jobs.
"""

from __future__ import annotations

import logging
import json
import subprocess
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from typing import Any

import httpx

from db.repositories.autopilot import update_source_status, is_video_processed
from db.repositories.source_ingestion import record_ingestion_atomic
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
        
        # Gap 204: Use a source-scoped lock to prevent concurrent polls for the same source
        from core.redis_utils import RobustRedisLock
        from core.config import settings
        import redis
        
        r = redis.from_url(settings.redis_url)
        lock_key = f"lock:source:{source_id}"
        # 10 minute timeout, fail fast if locked
        lock = RobustRedisLock(r, lock_key, timeout=600, blocking=False)
        
        try:
            with lock:
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
                
                # Transactional Ingestion
                # Note: We use a default 'v4' prompt for Autopilot
                new_job_id = record_ingestion_atomic(
                    source_id=source_id,
                    user_id=user_id,
                    video_id=vid,
                    video_url=vurl
                )
                
                # Gap 93: Stagger ingestion tasks by 10-60s to avoid thundering herd.
                # Autopilot polling happens in bursts; staggering prevents
                # resource exhaustion on the worker cluster.
                countdown = random.randint(10, 60)
                logger.info(
                    "[source=%s] New video found: %s. Scheduling job %s with %ds stagger...",
                    source_id, vid, new_job_id, countdown
                )
                
                # Dispatch to AI Pipeline
                dispatch_task(
                    "workers.pipeline.process_job",
                    job_id=new_job_id,
                    countdown=countdown  # Delay execution
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

        except RuntimeError:
            # Acquisition failed because blocking=False
            logger.warning("[Autopilot] [source=%s] Source already being polled. Skipping.", source_id)
            return 0
        except Exception as exc:
            error_msg = f"Polling failed: {str(exc)}"
            logger.error("[source=%s] %s", source_id, error_msg, exc_info=True)
            update_source_status(source_id, last_error=error_msg)
            return 0

    def _poll_youtube(self, config: dict) -> list[dict[str, str]]:
        """Use yt-dlp to get a paginated slice of the latest YouTube uploads."""
        channel_url = config.get("channel_url")
        if not channel_url:
            return []

        try:
            # metadata-only lookup for 3 most recent
            cmd = [
                "yt-dlp",
                "--get-id",
                "--flat-playlist",
                "--playlist-end", str(config.get("max_items", 20)),
                channel_url
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            video_ids = [vid.strip() for vid in result.stdout.split("\n") if vid.strip()]
            
            return [
                {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}
                for vid in video_ids
            ]
        except subprocess.TimeoutExpired as exc:
            logger.error("yt-dlp timed out while polling YouTube channel %s", channel_url)
            raise RuntimeError(f"yt-dlp timed out while polling {channel_url}") from exc
        except Exception as exc:
            logger.error("yt-dlp failed to poll YouTube channel %s: %s", channel_url, exc)
            raise
        
        return []

    def _poll_tiktok(self, config: dict) -> list[dict[str, str]]:
        """Use yt-dlp to get a paginated slice of the latest TikTok videos."""
        channel_url = config.get("channel_url")
        if not channel_url:
            return []

        try:
            cmd = [
                "yt-dlp",
                "--get-id",
                "--flat-playlist",
                "--playlist-end", str(config.get("max_items", 20)),
                channel_url
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            video_ids = [vid.strip() for vid in result.stdout.split("\n") if vid.strip()]
            
            return [
                {"id": vid, "url": f"https://www.tiktok.com/@user/video/{vid}"}
                for vid in video_ids
            ]
        except subprocess.TimeoutExpired as exc:
            logger.error("yt-dlp timed out while polling TikTok channel %s", channel_url)
            raise RuntimeError(f"yt-dlp timed out while polling {channel_url}") from exc
        except Exception as exc:
            logger.error("yt-dlp failed to poll TikTok channel %s: %s", channel_url, exc)
            raise 
            
        return []

    def _poll_rss(self, config: dict) -> list[dict[str, str]]:
        """Fetch RSS or Atom entries and convert them into ingestion jobs."""
        feed_url = config.get("feed_url") or config.get("rss_url") or config.get("url")
        if not feed_url:
            return []

        try:
            response = httpx.get(feed_url, timeout=30.0)
            response.raise_for_status()
            root = ET.fromstring(response.text)
        except Exception as exc:
            logger.error("RSS poll failed for %s: %s", feed_url, exc)
            raise

        max_items = int(config.get("max_items", 20))
        entries: list[dict[str, str]] = []

        if root.tag.endswith("rss") or root.find(".//channel") is not None:
            for item in root.findall(".//item")[:max_items]:
                item_id = (
                    item.findtext("guid")
                    or item.findtext("link")
                    or item.findtext("title")
                    or ""
                ).strip()
                link = (item.findtext("link") or feed_url).strip()
                if not link:
                    continue
                entries.append({"id": item_id or link, "url": link})
            return entries

        atom_ns = "{http://www.w3.org/2005/Atom}"
        for entry in root.findall(f".//{atom_ns}entry")[:max_items]:
            item_id = (entry.findtext(f"{atom_ns}id") or "").strip()
            link_el = entry.find(f"{atom_ns}link[@rel='alternate']")
            if link_el is None:
                link_el = entry.find(f"{atom_ns}link")
            link = (link_el.get("href") if link_el is not None else "") or ""
            link = link.strip()
            if not link:
                continue
            entries.append({"id": item_id or link, "url": urljoin(feed_url, link)})
        return entries

def get_source_ingestion_service() -> SourceIngestionService:
    return SourceIngestionService()
