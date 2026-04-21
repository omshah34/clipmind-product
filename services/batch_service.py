"""File: services/batch_service.py
Purpose: Orchestrates bulk job processing and multi-clip aggregation.
"""

import zipfile
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import List

from core.config import settings
from db.repositories.jobs import get_job
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

class BatchService:
    MAX_CONCURRENT_BATCH_JOBS = 3

    @staticmethod
    def trigger_batch_render(job_ids: List[str]):
        """
        Triggers rendering tasks for multiple jobs in parallel.
        Enforces a concurrency limit to prevent worker saturation.
        """
        # In a real distributed system, we'd check a Redis-based counter
        # For this MVP, we limit the number of jobs we enqueue at once
        batch_ids = job_ids[:BatchService.MAX_CONCURRENT_BATCH_JOBS]
        
        for job_id in batch_ids:
            logger.info("Enqueuing batch render for job: %s", job_id)
            # Re-using the existing render_clips task or full pipeline
            # Using the 'batch-export' queue (low-priority) if configured
            celery_app.send_task(
                "workers.pipeline.process_job",
                args=[job_id],
                queue="batch-export"
            )
            
        return len(batch_ids)

    @staticmethod
    def create_batch_zip(job_ids: List[str]) -> Path:
        """
        Aggregates all rendered clips from specified jobs into a single ZIP.
        Enables streamlined hand-off for agencies.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        zip_name = f"clipmind_batch_{timestamp}.zip"
        zip_path = Path(settings.local_storage_dir) / "exports" / zip_name
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for job_id in job_ids:
                job = get_job(job_id)
                if not job or not job.clips_json:
                    continue
                
                # Add clips
                for clip in job.clips_json:
                    # Resolve local path from URI (file://...)
                    clip_url = clip.get("clip_url")
                    if clip_url and clip_url.startswith("file://"):
                        from urllib.parse import urlparse, unquote
                        p = Path(unquote(urlparse(clip_url).path).lstrip("/"))
                        if p.exists():
                            # Path in ZIP: job_id/clip_index.mp4
                            arc_name = f"{job_id[:8]}/clip_{clip.get('clip_index')}.mp4"
                            zip_file.write(p, arc_name)
                
                # Add a README with captions/hashtags if available
                # (Future refinement)

        return zip_path
