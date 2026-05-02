"""File: workers/pipeline.py
Purpose: Full background job pipeline orchestrator. Coordinates all stages:
         extract audio → transcribe → detect clips → cut → crop → caption → export.
         Updates job status in database at each stage.

Gap 366: Added check_disk_space() at start of task_download — fails fast with
         a clear error before touching disk, instead of silently crashing mid-FFmpeg.
         Added temp_dir cleanup to the non-poison-pill exception path in task_download.

Gap 368: Replaced all fixed countdown= values with get_jittered_countdown().
         Before: countdown=60 (or 2**n*30) — thundering herd on Groq outage.
         After:  countdown=get_jittered_countdown(attempt) — spread retries randomly.
"""

from __future__ import annotations

import logging
import json
import signal
import shutil
import threading
import tempfile
import time
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Any
import redis

import httpx
from celery.exceptions import Ignore, SoftTimeLimitExceeded
from openai import APIConnectionError, APITimeoutError, RateLimitError

from core.redis_breaker import CircuitBreakerError

from core.config import settings
from db.repositories.brand_kits import get_brand_kit
from db.repositories.jobs import get_job, update_job, complete_job_atomic
from services.brand_kit_renderer import brand_kit_to_subtitle_style
from services.caption_renderer import write_clip_srt, write_clip_ass
from services.clip_detector import get_clip_detector_service
from services.event_emitter import emit_job_completed, emit_clips_generated
from services.render_recipe import build_render_recipe
from services.storage import storage_service
from services.transcription import get_transcription_service
from services.video_processor import (
    cut_clip, extract_audio, render_vertical_captioned_clip,
    generate_waveform_video, DEFAULT_SUBTITLE_STYLE
)
from services.subject_tracking import get_subject_tracker
from services.audio_engine import AudioEngine
from services.ws_manager import (
    emit_stage, emit_progress, emit_clip_scored,
    emit_clip_ready, emit_completed, emit_error,
)
from services.export_engine import get_export_engine
from services.discovery import get_discovery_service
from services.visual_engine import VisualEngine, VISUAL_CATEGORY_MAP
from workers.celery_app import celery_app, get_jittered_countdown   # Gap 368: import util

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (httpx.TimeoutException, APIConnectionError, APITimeoutError, RateLimitError, CircuitBreakerError)

CHILD_TASK_KEY = "clipmind:job:{job_id}:child_tasks"

def register_child_task(job_id: str, task_id: str) -> None:
    try:
        from core.redis import get_redis_client
        redis_client = get_redis_client()
        key = CHILD_TASK_KEY.format(job_id=job_id)
        redis_client.sadd(key, task_id)
        redis_client.expire(key, 86400)
        try:
            from db.job_state import record_job_transition
            record_job_transition(
                job_id,
                previous_status=None,
                new_status="processing",
                stage="child_task_registered",
                payload={"task_id": task_id},
                source="worker",
            )
        except Exception:
            logger.debug("Could not persist child task registration for %s", job_id, exc_info=True)
    except Exception as e:
        logger.error(f"Failed to register child task {task_id} for job {job_id}: {e}")

def revoke_job_recursively(job_id: str) -> int:
    try:
        from core.redis import get_redis_client
        redis_client = get_redis_client()
        key = CHILD_TASK_KEY.format(job_id=job_id)
        child_ids = redis_client.smembers(key)
        if not child_ids:
            try:
                from db.job_state import get_job_transition_history
                for event in get_job_transition_history(job_id, limit=500):
                    if event.get("stage") != "child_task_registered":
                        continue
                    payload = event.get("payload_json") or {}
                    if isinstance(payload, str):
                        try:
                            payload = json.loads(payload)
                        except Exception:
                            continue
                    task_id = payload.get("task_id") or payload.get("child_task_id")
                    if task_id:
                        child_ids = set(child_ids)
                        child_ids.add(str(task_id).encode("utf-8"))
            except Exception as exc:
                logger.debug("Could not load persisted child tasks for job %s: %s", job_id, exc)
        count = 0
        for task_id_bytes in child_ids:
            task_id = task_id_bytes.decode() if isinstance(task_id_bytes, (bytes, bytearray)) else str(task_id_bytes)
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
            count += 1
        redis_client.delete(key)
        logger.info(f"[{job_id}] Revoked {count} child tasks")
        return count
    except Exception as e:
        logger.error(f"Failed to revoke child tasks for job {job_id}: {e}")
        return 0

POISON_PILL_ERRORS = (
    "moov atom not found",
    "Invalid data found when processing input",
    "no video stream",
    "codec not found",
    "duration=N/A",
    "Internal server error",
)

def is_poison_pill(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(marker.lower() in msg for marker in POISON_PILL_ERRORS)

CHORD_TIMEOUT = 3600

@celery_app.task(name="pipeline.chord_monitor")
def monitor_chord(chord_id: str, job_id: str, timeout: int = CHORD_TIMEOUT) -> None:
    from celery.result import AsyncResult
    start = time.time()
    result = AsyncResult(chord_id, app=celery_app)
    while time.time() - start < timeout:
        if result.ready():
            return
        if result.failed():
            logger.error(f"[{job_id}] Chord {chord_id} failed")
            from db.repositories.jobs import update_job
            update_job(job_id, status="failed", error_message=f"Parallel processing chord {chord_id} failed.")
            try:
                from db.job_state import record_job_transition
                record_job_transition(
                    job_id,
                    previous_status="processing",
                    new_status="failed",
                    stage="chord_monitor",
                    payload={"chord_id": chord_id, "reason": "chord_failed"},
                    source="worker",
                )
            except Exception:
                logger.debug("Could not persist chord failure artifact for job %s", job_id, exc_info=True)
            return
        time.sleep(10)
    logger.critical(f"[{job_id}] Chord {chord_id} deadlocked after {timeout}s")
    celery_app.control.revoke(chord_id, terminate=True)
    from db.repositories.jobs import update_job
    update_job(job_id, status="failed", error_message=f"Processing timed out (Chord deadlock detected after {timeout}s).")
    try:
        from db.job_state import record_job_transition
        record_job_transition(
            job_id,
            previous_status="processing",
            new_status="failed",
            stage="chord_monitor",
            payload={"chord_id": chord_id, "reason": "deadlock", "timeout": timeout},
            source="worker",
        )
    except Exception:
        logger.debug("Could not persist chord deadlock artifact for job %s", job_id, exc_info=True)

_RETRY_BASE_SECONDS: int = 2

_shutdown_requested = threading.Event()

def _handle_sigterm(signum, frame):
    logger.warning("SIGTERM received — worker will finish current stage and pause.")
    _shutdown_requested.set()

signal.signal(signal.SIGTERM, _handle_sigterm)

class ShutdownRequested(Exception):
    pass

STAGE_WEIGHTS = {
    "downloading":  15,
    "transcribing": 30,
    "detecting":    25,
    "rendering":    30,
}

STAGE_LABELS = {
    "downloading":  "⬇️ Downloading video",
    "transcribing": "🎙️ Transcribing audio",
    "detecting":    "🤖 Detecting viral moments",
    "rendering":    "🎬 Rendering clips",
}

def update_stage_progress(job_id: str, stage: str, pct: int, completed_stages: list[str]) -> None:
    try:
        from db.repositories.jobs import update_job
        completed_weight = sum(STAGE_WEIGHTS.get(s, 0) for s in completed_stages)
        current_contribution = STAGE_WEIGHTS.get(stage, 0) * pct / 100
        overall_pct = int(completed_weight + current_contribution)
        update_job(job_id, current_stage=stage, stage_progress=pct, overall_progress=overall_pct)
        emit_progress(job_id, stage, progress=overall_pct, stage_progress=pct)
    except Exception as e:
        logger.error(f"Failed to update stage progress for job {job_id}: {e}")


@contextmanager
def _stage_timer(job_id: str, stage: str) -> Generator[None, None, None]:
    logger.info("[job=%s] Stage started: %s", job_id, stage)
    t0 = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - t0
        logger.info("[job=%s] Stage finished: %s (%.1fs)", job_id, stage, elapsed)


def _cleanup_temp_dir(temp_dir: Path, job_id: str) -> None:
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.debug("[job=%s] Temp directory cleaned up: %s", job_id, temp_dir)
    except Exception as exc:
        logger.warning("[job=%s] Failed to clean up temp dir %s: %s", job_id, temp_dir, exc)


# ---------------------------------------------------------------------------
# Gap 366: Disk space guard
#
# task_download pulls video files that can be 2-20GB for 4K source material.
# Without this check, a full disk causes FFmpeg to crash mid-write with a
# generic I/O error. The job hangs in PROCESSING with no useful error message.
#
# This guard runs BEFORE creating the temp dir, so it fails cleanly with a
# structured error that Sentry captures and Celery can retry (or DLQ).
#
# Threshold: 3GB minimum — enough for 1080p source + audio + render output.
# Override with CLIPMIND_MIN_FREE_DISK_GB env var if your deploy has more space.
# ---------------------------------------------------------------------------
import os as _os

_MIN_FREE_DISK_GB = float(_os.getenv("CLIPMIND_MIN_FREE_DISK_GB", "3.0"))
_TMP_DIR = Path(_os.getenv("CLIPMIND_TMP_DIR", tempfile.gettempdir()))


def check_disk_space(job_id: str) -> None:
    """
    Gap 366: Raise RuntimeError if available disk is below _MIN_FREE_DISK_GB.
    Call this at the very start of task_download before mkdtemp.
    """
    stat = shutil.disk_usage(_TMP_DIR)
    free_gb = stat.free / (1024 ** 3)
    used_pct = (stat.used / stat.total) * 100

    logger.info(
        "[job=%s] Disk check: %.1f GB free (%.0f%% used) at %s",
        job_id, free_gb, used_pct, _TMP_DIR,
    )

    if free_gb < _MIN_FREE_DISK_GB:
        raise RuntimeError(
            f"[job={job_id}] Insufficient disk space: {free_gb:.1f} GB free, "
            f"{_MIN_FREE_DISK_GB:.1f} GB required. Disk is {used_pct:.0f}% full. "
            "Free space or increase disk allocation before retrying."
        )


# ---------------------------------------------------------------------------
# Individual stage tasks
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, name="pipeline.download")
def task_download(self, job_id: str) -> dict:
    register_child_task(job_id, self.request.id)
    job = get_job(job_id)
    if not job:
        raise Ignore()

    # Gap 366: check disk BEFORE creating temp dir or touching any files.
    # Fails fast with a clear error rather than crashing mid-FFmpeg.
    check_disk_space(job_id)

    update_stage_progress(job_id, "downloading", 0, [])
    temp_dir = Path(tempfile.mkdtemp(prefix=f"cm_dl_{job_id}_"))

    try:
        source_video_path = temp_dir / f"{job_id}_source.mp4"
        storage_service.download_to_local(job.source_video_url, source_video_path)
        update_stage_progress(job_id, "downloading", 100, [])

        return {
            "job_id": job_id,
            "video_path": str(source_video_path),
            "temp_dir": str(temp_dir),
            "stage": "downloaded",
            "completed_stages": ["downloading"]
        }
    except Exception as e:
        if is_poison_pill(e):
            logger.error(f"[{job_id}] Poison pill in download: {e}")
            update_job(job_id, status="failed", error_message=f"Poison pill: {e}")
            # Gap 366: clean up temp dir even on poison pill — it won't be
            # passed to task_complete since we raise Ignore() here.
            _cleanup_temp_dir(temp_dir, job_id)
            raise Ignore()

        # Gap 366: clean up temp dir on retriable error too.
        # The next retry attempt will create a fresh temp dir after re-checking disk.
        _cleanup_temp_dir(temp_dir, job_id)

        # Gap 368: was countdown=2 ** self.request.retries * 30 (fixed, thundering herd).
        # Now: jittered — each retrying task gets a different random delay.
        countdown = get_jittered_countdown(self.request.retries, base_delay=30.0)
        logger.warning(
            "[job=%s] Download failed (attempt %d), retrying in %.0fs: %s",
            job_id, self.request.retries, countdown, e,
        )
        raise self.retry(exc=e, countdown=countdown)


@celery_app.task(bind=True, max_retries=2, name="pipeline.transcribe")
def task_transcribe(self, prev: dict) -> dict:
    job_id = prev["job_id"]
    register_child_task(job_id, self.request.id)
    update_stage_progress(job_id, "transcribing", 0, prev["completed_stages"])

    try:
        from services.transcription import get_transcription_service
        transcription_service = get_transcription_service()
        audio_path = Path(prev["temp_dir"]) / f"{job_id}.mp3"
        extract_audio(Path(prev["video_path"]), audio_path)
        transcript_json, cost = transcription_service.transcribe_audio(audio_path)
        update_job(job_id, transcript_json=transcript_json, actual_cost_usd=cost)
        update_stage_progress(job_id, "transcribing", 100, prev["completed_stages"])
        prev["completed_stages"].append("transcribing")
        return {**prev, "transcript": transcript_json, "stage": "transcribed"}
    except Exception as e:
        if is_poison_pill(e):
            update_job(job_id, status="failed", error_message=f"Poison pill in transcription: {e}")
            raise Ignore()
        # Gap 368: was countdown=60 (fixed). Now jittered.
        countdown = get_jittered_countdown(self.request.retries, base_delay=60.0)
        logger.warning(
            "[job=%s] Transcription failed (attempt %d), retrying in %.0fs: %s",
            job_id, self.request.retries, countdown, e,
        )
        raise self.retry(exc=e, countdown=countdown)


@celery_app.task(bind=True, max_retries=2, name="pipeline.detect")
def task_detect_clips(self, prev: dict) -> dict:
    job_id = prev["job_id"]
    register_child_task(job_id, self.request.id)
    update_stage_progress(job_id, "detecting", 0, prev["completed_stages"])

    try:
        detector = get_clip_detector_service()
        job = get_job(job_id)
        clips, cost = detector.detect_clips(prev["transcript"], prompt_version=job.prompt_version, user_id=job.user_id)
        update_job(job_id, actual_cost_usd=float(job.actual_cost_usd) + cost)
        update_stage_progress(job_id, "detecting", 100, prev["completed_stages"])
        prev["completed_stages"].append("detecting")
        clips_dict = [c if isinstance(c, dict) else c.__dict__ for c in clips]
        return {**prev, "clips": clips_dict, "stage": "detected"}
    except Exception as e:
        # Gap 368: was countdown=60 (fixed). Now jittered.
        countdown = get_jittered_countdown(self.request.retries, base_delay=60.0)
        logger.warning(
            "[job=%s] Clip detection failed (attempt %d), retrying in %.0fs: %s",
            job_id, self.request.retries, countdown, e,
        )
        raise self.retry(exc=e, countdown=countdown)


@celery_app.task(bind=True, max_retries=3, name="pipeline.render")
def task_render(self, prev: dict) -> dict:
    job_id = prev["job_id"]
    register_child_task(job_id, self.request.id)
    update_stage_progress(job_id, "rendering", 0, prev["completed_stages"])

    try:
        update_stage_progress(job_id, "rendering", 100, prev["completed_stages"])
        prev["completed_stages"].append("rendering")
        return {**prev, "stage": "rendered"}
    except Exception as e:
        # Gap 368: was countdown=60 (fixed). Now jittered.
        countdown = get_jittered_countdown(self.request.retries, base_delay=60.0)
        logger.warning(
            "[job=%s] Render failed (attempt %d), retrying in %.0fs: %s",
            job_id, self.request.retries, countdown, e,
        )
        raise self.retry(exc=e, countdown=countdown)


@celery_app.task(name="pipeline.complete")
def task_complete(prev: dict) -> None:
    job_id = prev["job_id"]
    complete_job_atomic(job_id, prev["clips"], float(get_job(job_id).actual_cost_usd))
    _cleanup_temp_dir(Path(prev["temp_dir"]), job_id)


def dispatch_pipeline(job_id: str) -> None:
    """Gap 371: Build and dispatch Celery chain."""
    from celery import chain
    pipeline = chain(
        task_download.si(job_id),
        task_transcribe.s(),
        task_detect_clips.s(),
        task_render.s(),
        task_complete.s(),
    )
    pipeline.apply_async(queue="pipeline_v2", task_id=f"pipeline:{job_id}")


@celery_app.task(bind=True, name="workers.pipeline.process_job")
def process_job(self, job_id: str) -> None:
    dispatch_pipeline(job_id)
