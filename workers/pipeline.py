"""File: workers/pipeline.py
Purpose: Full background job pipeline orchestrator. Coordinates all stages:
         extract audio → transcribe → detect clips → cut → crop → caption → export.
         Updates job status in database at each stage.

Improvements over v3:
  - Per-clip except now re-raises TRANSIENT_ERRORS so upload timeouts trigger
    a proper job retry instead of silently skipping the clip
  - Partial progress (successful clip URLs) saved to DB after each clip so a
    later failure doesn't lose already-uploaded clips and avoids redundant
    re-processing on retry
  - All-clips-failed case distinguished from "no clips detected": job is marked
    "failed" (not "completed") when every detected clip fails processing, with
    a clear error_message so operators aren't misled by completed/0-clips rows
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

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
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (httpx.TimeoutException, APIConnectionError, APITimeoutError, RateLimitError, CircuitBreakerError)

_RETRY_BASE_SECONDS: int = 2   # countdown = _RETRY_BASE_SECONDS ** retry_number


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextmanager
def _stage_timer(job_id: str, stage: str) -> Generator[None, None, None]:
    """Log entry/exit of a pipeline stage with elapsed time."""
    logger.info("[job=%s] Stage started: %s", job_id, stage)
    t0 = time.monotonic()
    try:
        yield
    finally:
        elapsed = time.monotonic() - t0
        logger.info("[job=%s] Stage finished: %s (%.1fs)", job_id, stage, elapsed)


def _cleanup_temp_dir(temp_dir: Path, job_id: str) -> None:
    """Remove a temp directory, logging any errors without re-raising."""
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.debug("[job=%s] Temp directory cleaned up: %s", job_id, temp_dir)
    except Exception as exc:
        logger.warning("[job=%s] Failed to clean up temp dir %s: %s", job_id, temp_dir, exc)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True, 
    name="workers.pipeline.process_job",
    soft_time_limit=1800,  # 30 min for full pipeline
    time_limit=1860,
)
def process_job(self, job_id: str) -> list[dict]:
    job = get_job(job_id)
    if job is None:
        logger.warning("Job %s not found in DB; ignoring task.", job_id)
        raise Ignore()
        
    # Gap 201: Prevent race condition if user cancels exactly as worker starts
    if job.status == "completed":
        logger.info("Job %s is already completed; ignoring duplicate task.", job_id)
        raise Ignore()

    if job.status in ["cancelled", "failed"]:
        logger.warning("Job %s is already %s; ignoring task.", job_id, job.status)
        raise Ignore()

    current_stage = "queued"
    actual_cost = float(job.actual_cost_usd)
    pipeline_start = time.monotonic()
    transcription_service = get_transcription_service()
    clip_detector_service = get_clip_detector_service()
    subject_tracker = get_subject_tracker()
    export_engine = get_export_engine()
    discovery_service = get_discovery_service()
    subject_tracking_enabled = bool(getattr(subject_tracker, "enabled", True))

    # Temp dir created here so both success and failure paths can clean it up.
    temp_dir = Path(tempfile.mkdtemp(prefix=f"clipmind_{job.id}_"))

    try:
        update_job(
            job.id,
            status="queued",
            failed_stage=None,
            error_message=None,
            retry_count=self.request.retries,
        )

        # ------------------------------------------------------------------ #
        # 1. Download source video — into temp_dir so cleanup is guaranteed
        # ------------------------------------------------------------------ #
        current_stage = "downloading"
        emit_stage(job_id, current_stage, progress=5)
        with _stage_timer(job_id, current_stage):
            update_job(job.id, status=current_stage)
            source_video_path = temp_dir / f"{job.id}_source.mp4"
            storage_service.download_to_local(
                job.source_video_url,
                source_video_path,
            )
            emit_progress(job_id, current_stage, progress=15)
            
            # -- Gap 63: Generate Preview Proxy ----------------------------
            try:
                current_stage = "generating_proxy"
                with _stage_timer(job_id, current_stage):
                    update_job(job.id, status=current_stage)
                    from services.video_processor import generate_proxy_video, get_video_dimensions

                    source_width, source_height = get_video_dimensions(source_video_path)
                    if source_width <= 1280 and source_height <= 720 and source_video_path.suffix.lower() in {".mp4", ".m4v", ".mov"}:
                        update_job(job.id, proxy_video_url=job.source_video_url)
                        logger.info(
                            "[job=%s] Source is already proxy-friendly (%sx%s); reusing source video URL",
                            job_id,
                            source_width,
                            source_height,
                        )
                    else:
                        proxy_path = temp_dir / f"{job.id}_proxy.mp4"
                        generate_proxy_video(source_video_path, proxy_path)
                        proxy_url = storage_service.upload_file(proxy_path, "proxies", f"{job.id}_proxy.mp4")
                        update_job(job.id, proxy_video_url=proxy_url)
                        logger.info("[job=%s] Preview proxy generated and uploaded", job_id)
            except Exception as proxy_exc:
                # Proxy is non-critical for pipeline success, just for UI smoothness
                logger.warning("[job=%s] Proxy generation failed: %s", job_id, proxy_exc)

        # ------------------------------------------------------------------ #
        # 2. Extract audio (Branch: skip if source is already audio)
        # ------------------------------------------------------------------ #
        is_audio_only = source_video_path.suffix.lower() in [".mp3", ".wav", ".m4a"]
        audio_path = temp_dir / f"{job.id}.mp3"

        if isinstance(job.transcript_json, dict) and job.transcript_json.get("segments"):
            transcript_json = job.transcript_json
            current_stage = "transcribing"
            emit_stage(job_id, current_stage, progress=50, reused=True)
            update_job(job.id, status=current_stage)
            logger.info("[job=%s] Reusing existing transcript; skipping audio extraction/transcription", job_id)
            if job.audio_url:
                try:
                    storage_service.download_to_local(job.audio_url, audio_path)
                except Exception as audio_exc:
                    logger.warning("[job=%s] Existing audio download failed: %s. Re-extracting audio.", job_id, audio_exc)
                    if is_audio_only:
                        shutil.copy(source_video_path, audio_path)
                    else:
                        extract_audio(source_video_path, audio_path)
            elif is_audio_only:
                shutil.copy(source_video_path, audio_path)
            else:
                extract_audio(source_video_path, audio_path)
                audio_url = storage_service.upload_file(audio_path, "audio", f"{job.id}.mp3")
                update_job(job.id, audio_url=audio_url)
        else:
            if is_audio_only:
                logger.info("[job=%s] Source is audio-only. Skipping extraction.", job_id)
                shutil.copy(source_video_path, audio_path)
            else:
                current_stage = "extracting_audio"
                emit_stage(job_id, current_stage, progress=20)
                with _stage_timer(job_id, current_stage):
                    update_job(job.id, status=current_stage)
                    extract_audio(source_video_path, audio_path)
                    audio_url = storage_service.upload_file(audio_path, "audio", f"{job.id}.mp3")
                    update_job(job.id, audio_url=audio_url)
                    emit_progress(job_id, current_stage, progress=30)

            # ------------------------------------------------------------------ #
            # 3. Transcribe
            # ------------------------------------------------------------------ #
            current_stage = "transcribing"
            emit_stage(job_id, current_stage, progress=35)
            with _stage_timer(job_id, current_stage):
                update_job(job.id, status=current_stage)
                
                # Gap 72: Fetch vocabulary hints from brand kit if available
                vocab_hints = None
                if job.brand_kit_id:
                    brand_kit = get_brand_kit(job.brand_kit_id)
                    if brand_kit and brand_kit.vocabulary_hints:
                        vocab_hints = brand_kit.vocabulary_hints
                        logger.info("[job=%s] Using %d vocabulary hints for transcription", job_id, len(vocab_hints))

                transcript_json, transcription_cost = transcription_service.transcribe_audio(
                    audio_path,
                    language=job.language,
                    vocabulary_hints=vocab_hints
                )
                actual_cost += transcription_cost
                word_count = sum(len(s.get("words", [])) for s in transcript_json.get("segments", []))
                update_job(
                    job.id,
                    transcript_json=transcript_json,
                    actual_cost_usd=round(actual_cost, 6),
                )
                emit_progress(job_id, current_stage, progress=50, words=word_count)
                
                # -- AI Semantic Discovery Indexing (Phase 3) --
                try:
                    with _stage_timer(job_id, "indexing_semantics"):
                        # This is non-blocking in Phase 3 for MVP
                        # (In-memory/local-index is fast)
                        import asyncio
                        asyncio.run(discovery_service.add_job_to_index(job.id, transcript_json))
                        logger.info("[job=%s] Job indexed for AI semantic discovery", job_id)
                except Exception as idx_exc:
                    logger.warning("[job=%s] Semantic indexing failed: %s", job_id, idx_exc)

        # ------------------------------------------------------------------ #
        # 4. Detect clips
        # ------------------------------------------------------------------ #
        current_stage = "detecting_clips"
        emit_stage(job_id, current_stage, progress=55)
        with _stage_timer(job_id, current_stage):
            update_job(job.id, status=current_stage)
            detected_clips, llm_cost = clip_detector_service.detect_clips(
                transcript_json,
                prompt_version=job.prompt_version,
                user_id=job.user_id,
            )
            actual_cost += llm_cost
            update_job(job.id, actual_cost_usd=round(actual_cost, 6))
            emit_progress(job_id, current_stage, progress=65, candidates_found=len(detected_clips))
            # Emit individual clip scores
            for dc in detected_clips:
                emit_clip_scored(
                    job_id, int(dc.get("clip_index", 0)),
                    {k: dc.get(k, 0) for k in ["hook_score", "emotion_score", "clarity_score", "story_score", "virality_score"]},
                    reason=dc.get("reason", ""),
                )

        if not detected_clips:
            logger.info("[job=%s] No clips detected; marking completed.", job_id)
            complete_job_atomic(
                job.id,
                clips=[],
                actual_cost=actual_cost,
            )
            emit_completed(job_id, 0, 0.0, time.monotonic() - pipeline_start)
            return []

        # ------------------------------------------------------------------ #
        # 5. Cut → Caption → Export each clip
        # ------------------------------------------------------------------ #
        final_clips: list[dict] = []
        skipped_clip_indices: list[int] = []

        for clip in detected_clips:
            clip_index = clip.get("clip_index")
            if clip_index is None:
                logger.warning("[job=%s] Clip missing clip_index; skipping.", job_id)
                continue
            clip_index = int(clip_index)

            raw_clip_path   = temp_dir / f"clip_{clip_index}_raw.mp4"
            ass_path        = temp_dir / f"clip_{clip_index}.ass"
            srt_path        = temp_dir / f"clip_{clip_index}.srt"
            final_clip_path = temp_dir / f"clip_{clip_index}_final.mp4"

            try:
                # -- Cut ----------------------------------------------------
                current_stage = f"cutting_clip_{clip_index}"
                clip_progress_base = 70 + int((clip_index / len(detected_clips)) * 25)
                emit_stage(job_id, "cutting_clip", progress=clip_progress_base, clip_index=clip_index, total_clips=len(detected_clips))
                with _stage_timer(job_id, current_stage):
                    update_job(job.id, status="cutting_video")
                    if is_audio_only:
                        # For audio only, we still need to cut the raw audio segment first
                        audio_clip_path = temp_dir / f"clip_{clip_index}_audio.mp3"
                        cut_clip(audio_path, float(clip["start_time"]), float(clip["end_time"]), audio_clip_path)
                        
                        # -- Phase 6: Audio-to-Viral Generative Stage --
                        with _stage_timer(job_id, "generating_waveform"):
                            generate_waveform_video(
                                audio_clip_path,
                                raw_clip_path,
                                duration=float(clip["end_time"]) - float(clip["start_time"]),
                                bg_color="black" # Default, or pull from brand kit later
                            )
                    else:
                        cut_clip(
                            source_video_path,
                            start_time=float(clip["start_time"]),
                            end_time=float(clip["end_time"]),
                            output_path=raw_clip_path,
                        )

                # -- Write ASS + Render captions ----------------------------
                current_stage = f"captioning_clip_{clip_index}"
                emit_stage(job_id, "captioning_clip", progress=clip_progress_base + 5, clip_index=clip_index)
                with _stage_timer(job_id, current_stage):
                    update_job(job.id, status="rendering_captions")
                    
                    # Decide on styling preset
                    style_preset = "hormozi" # Default for viral "wow" factor
                    
                    # Load brand kit if job references one
                    subtitle_style = DEFAULT_SUBTITLE_STYLE
                    if job.brand_kit_id:
                        brand_kit = get_brand_kit(job.brand_kit_id)
                        if brand_kit:
                            subtitle_style = brand_kit_to_subtitle_style(brand_kit)
                            # If brand kit has a specific preset name, we use it
                            # For now, we default to Hormozi as the "Pro" default
                            logger.debug(
                                "[job=%s] Using brand kit '%s' for caption styling",
                                job_id, brand_kit.name
                            )
                    
                    subject_centers: list[float] = []
                    detected_face_count = 0
                    primary_face_area_ratio: float | None = None
                    
                    if subject_tracking_enabled:
                        try:
                            with _stage_timer(job_id, current_stage):
                                update_job(job.id, status="reframing")

                                tracking = subject_tracker.analyze_subjects(raw_clip_path, count=2)
                                detected_face_count = tracking.detected_face_count
                                primary_face_area_ratio = tracking.primary_face_area_ratio
                                subject_centers = list(tracking.centers[:detected_face_count]) if detected_face_count > 0 else []
                        except Exception as exc:
                            logger.info("[job=%s] Subject tracking skipped for clip %d: %s. Using center-crop.", job_id, clip_index, exc)
                            subject_centers = []
                            detected_face_count = 0
                            primary_face_area_ratio = None
                    else:
                        logger.debug("[job=%s] Subject tracking disabled for clip %d; using center-crop.", job_id, clip_index)

                    # -- Render Captions & Watermark ---------------------------
                    try:
                        # Phase 2: Audio Waveform Transient Sync (Deep Sync)
                        transients = None
                        try:
                            with _stage_timer(job_id, "detecting_transients"):
                                update_job(job.id, status="syncing_audio")
                                # Detect transients for the specific clip segment
                                transients = AudioEngine.get_transients(
                                    audio_path, 
                                    start_time=float(clip["start_time"]), 
                                    end_time=float(clip["end_time"])
                                )
                                logger.info("[job=%s] Detected %d transients for clip %d", job_id, len(transients), clip_index)
                        except Exception as sync_exc:
                            logger.info("[job=%s] Audio sync unavailable for clip %d: %s. Using default timing.", job_id, clip_index, sync_exc)

                        # Gap 107: Also generate a sidecar SRT for the user
                        write_clip_srt(
                            job.transcript_json,
                            clip_start_time=float(clip["start_time"]),
                            clip_end_time=float(clip["end_time"]),
                            output_path=srt_path
                        )
                        
                        # Handle Watermark
                        watermark_path = None
                        if job.brand_kit_id:
                            brand_kit = get_brand_kit(job.brand_kit_id)
                            if brand_kit and brand_kit.watermark_url:
                                watermark_path = temp_dir / f"watermark_{job.brand_kit_id}.png"
                                try:
                                    storage_service.download_to_local(brand_kit.watermark_url, watermark_path)
                                    logger.debug("[job=%s] Watermark downloaded for rendering", job_id)
                                except Exception as wm_exc:
                                    logger.warning("[job=%s] Failed to download watermark: %s. Proceeding without it.", job_id, wm_exc)
                                    watermark_path = None


                        # -- Headline Overlay (Phase 4) -------------
                        headline = None
                        try:
                            with _stage_timer(job_id, "generating_social_pulse"):
                                update_job(job.id, status="generating_metadata")
                                # Use engine to get viral headlines/caption
                                import asyncio as _asyncio
                                pulse = _asyncio.run(export_engine.generate_social_pulse(clip))
                                headline = pulse.get("headlines", [None])[0]
                                logger.info("[job=%s] Generated headline for clip %d: %s", job_id, clip_index, headline)
                                # We can also enrich the clip object here
                                clip["hook_headlines"] = pulse.get("headlines", [])
                                clip["social_caption"] = pulse.get("caption", "")
                                clip["social_hashtags"] = pulse.get("hashtags", [])
                        except Exception as pulse_exc:
                            logger.warning("[job=%s] Social pulse generation failed: %s", job_id, pulse_exc)

                        render_recipe = build_render_recipe(
                            clip,
                            transcript_json=job.transcript_json,
                            clip_start_time=float(clip["start_time"]),
                            clip_end_time=float(clip["end_time"]),
                            subject_centers=subject_centers,
                            detected_face_count=detected_face_count,
                            primary_face_area_ratio=primary_face_area_ratio,
                            social_pulse_headline=headline,
                            watermark_enabled=bool(watermark_path),
                        )
                        clip["layout_type"] = render_recipe["layout_type"]
                        clip["visual_mode"] = render_recipe["visual_mode"]
                        clip["selected_hook"] = render_recipe["selected_hook"]
                        clip["render_recipe"] = render_recipe

                        layout_type = render_recipe["layout_type"]
                        write_clip_ass(
                            job.transcript_json,
                            clip_start_time=float(clip["start_time"]),
                            clip_end_time=float(clip["end_time"]),
                            output_path=ass_path,
                            preset_name=str(render_recipe.get("caption_preset") or "hormozi"),
                            transients=transients,
                            layout_type=layout_type,
                        )
                        render_vertical_captioned_clip(
                            raw_clip_path, ass_path, final_clip_path,
                            style=subtitle_style,
                            subject_centers=subject_centers,
                            layout_type=layout_type,
                            watermark_path=watermark_path,
                            headline=render_recipe["selected_hook"],
                            screen_focus=render_recipe["screen_focus"],
                            audio_profile=render_recipe["audio_profile"],
                            render_recipe=render_recipe,
                        )
                        # -- B-Roll Pulse Cutaway Injection (Phase 3) --
                        if settings.enable_contextual_broll:
                            try:
                                keywords = clip.get("hook_headlines", []) + [clip.get("reason", "")]
                                import asyncio as _asyncio
                                broll_meta = _asyncio.run(VisualEngine.find_contextual_broll(keywords))

                                if broll_meta:
                                    with _stage_timer(job_id, "applying_broll"):
                                        update_job(job.id, status="applying_broll")
                                        broll_specs = []
                                        for i, b in enumerate(broll_meta):
                                            b_local = temp_dir / f"broll_{clip_index}_{i}.mp4"
                                            storage_service.download_to_local(b["url"], b_local)
                                            clip_duration = float(clip["end_time"]) - float(clip["start_time"])
                                            target_start = (clip_duration / (len(broll_meta) + 1)) * (i + 1)
                                            broll_specs.append({
                                                "path": b_local,
                                                "start": target_start,
                                                "duration": min(3.0, clip_duration / 4),
                                            })

                                        broll_output = temp_dir / f"clip_{clip_index}_brolled.mp4"
                                        from services.video_processor import apply_broll_cutaways
                                        apply_broll_cutaways(final_clip_path, broll_specs, broll_output)
                                        shutil.copy2(broll_output, final_clip_path)
                                        logger.info("[job=%s] Applied %d B-roll cutaways to clip %d", job_id, len(broll_specs), clip_index)
                                    
                            except Exception as broll_exc:
                                logger.info("[job=%s] B-Roll injection skipped for clip %d: %s", job_id, clip_index, broll_exc)

                    except Exception as render_exc:
                        logger.warning(
                            "[job=%s] Caption rendering failed for clip %d: %s. Falling back to raw cut.",
                            job_id, clip_index, render_exc
                        )
                        # Fallback: Copy raw clip to final path so the job doesn't fail
                        shutil.copy2(raw_clip_path, final_clip_path)

                # -- Upload -------------------------------------------------
                current_stage = f"exporting_clip_{clip_index}"
                emit_stage(job_id, "exporting_clip", progress=clip_progress_base + 10, clip_index=clip_index)
                with _stage_timer(job_id, current_stage):
                    update_job(job.id, status="exporting")
                    clip_url = storage_service.upload_file(
                        final_clip_path,
                        "clips",
                        f"{job.id}_clip_{clip_index}.mp4",
                    )
                    # Gap 107: Upload sidecar SRT
                    srt_url = storage_service.upload_file(
                        srt_path,
                        "clips",
                        f"{job.id}_clip_{clip_index}.srt"
                    )

            except TRANSIENT_ERRORS:
                # Upload timeouts, rate limits, etc. must reach the outer
                # retry handler — not be silently swallowed as a skipped clip.
                raise

            except Exception as exc:
                # Permanent per-clip failures (bad video segment, corrupt SRT,
                # etc.) are logged and skipped so remaining clips can proceed.
                logger.error(
                    "[job=%s] Clip %d failed permanently at stage '%s': %s",
                    job_id, clip_index, current_stage, exc,
                    exc_info=True,
                )
                skipped_clip_indices.append(clip_index)
                continue

            final_clip = {**clip, "clip_url": clip_url, "srt_url": srt_url}
            final_clips.append(final_clip)

            # Persist partial progress after each successful clip so a later
            # failure doesn't lose already-uploaded URLs and avoids redundant
            # re-processing on retry.
            update_job(job.id, clips_json=final_clips)

            # Emit clip ready event
            emit_clip_ready(
                job_id, clip_index,
                duration=float(clip.get("end_time", 0)) - float(clip.get("start_time", 0)),
                final_score=float(clip.get("final_score", 0)),
            )

            logger.info(
                "[job=%s] Clip %d/%d done. URL: %s",
                job_id, clip_index, len(detected_clips), clip_url,
            )

        # ------------------------------------------------------------------ #
        # 6. Mark completed — distinguish all-failed from partial/full success
        # ------------------------------------------------------------------ #
        if not final_clips:
            # Every detected clip failed permanently — this is not the same as
            # "no clips detected". Mark failed so operators aren't misled by a
            # completed/0-clips row in the DB.
            error_msg = (
                f"All {len(detected_clips)} detected clip(s) failed during processing. "
                f"Failed indices: {skipped_clip_indices}"
            )
            logger.error("[job=%s] %s", job_id, error_msg)
            update_job(
                job.id,
                status="failed",
                clips_json=[],
                actual_cost_usd=round(actual_cost, 6),
                failed_stage=current_stage,
                error_message=error_msg,
            )
            return []

        if skipped_clip_indices:
            logger.warning(
                "[job=%s] Pipeline completed with %d/%d clip(s). Skipped indices: %s",
                job_id, len(final_clips), len(detected_clips), skipped_clip_indices,
            )

        complete_job_atomic(
            job.id,
            clips=final_clips,
            actual_cost=actual_cost,
        )
        processing_time = time.monotonic() - pipeline_start
        best_score = max((float(c.get("final_score", 0)) for c in final_clips), default=0.0)
        emit_completed(job_id, len(final_clips), best_score, processing_time)
        logger.info(
            "[job=%s] Pipeline complete. %d clip(s). Total cost: $%.6f",
            job_id, len(final_clips), actual_cost,
        )
        
        # Emit webhooks for job completion
        if job.user_id:
            try:
                emit_job_completed(
                    job_id=job.id,
                    user_id=job.user_id,
                    status="completed",
                    clips_count=len(final_clips),
                    cost_usd=round(actual_cost, 6),
                )
                emit_clips_generated(
                    job_id=job.id,
                    user_id=job.user_id,
                    clips=final_clips,
                )
            except Exception as exc:
                logger.error("[job=%s] Failed to emit webhooks: %s", job_id, exc)
        
        return final_clips

    # ---------------------------------------------------------------------- #
    # Transient errors — retry with exponential backoff
    # ---------------------------------------------------------------------- #
    except TRANSIENT_ERRORS as exc:
        retry_count = self.request.retries + 1
        logger.warning(
            "[job=%s] Transient error at stage '%s' (attempt %d): %s",
            job_id, current_stage, retry_count, exc,
        )
        # Gap 243: Handle CircuitBreaker specifically with a long cooldown
        if isinstance(exc, CircuitBreakerError):
            countdown = 600  # 10 minutes
            logger.info("[job=%s] Circuit open. Scheduling retry in %ds.", job_id, countdown)
            # We allow more retries for circuit breaker since it's a platform-wide cooldown
            raise self.retry(exc=exc, countdown=countdown, max_retries=20)

        if retry_count <= settings.job_retry_limit:
            update_job(
                job.id,
                status="retrying",
                retry_count=retry_count,
                failed_stage=current_stage,
                error_message=str(exc),
            )
            # Gap 19: Standardized exponential backoff (60s, 120s, 240s...)
            countdown = 2 ** self.request.retries * 60
            raise self.retry(exc=exc, countdown=countdown)

        update_job(
            job.id,
            status="failed",
            retry_count=retry_count,
            failed_stage=current_stage,
            error_message=str(exc),
        )
        raise

    # ---------------------------------------------------------------------- #
    # Unrecoverable errors — fail immediately
    # ---------------------------------------------------------------------- #
    except SoftTimeLimitExceeded:
        logger.error("[job=%s] Soft time limit exceeded at stage '%s'.", job_id, current_stage)
        update_job(
            job.id,
            status="failed",
            failed_stage=current_stage,
            error_message="Task timed out",
            retry_count=self.request.retries,
        )
        raise

    except Exception as exc:
        logger.exception("[job=%s] Unrecoverable error at stage '%s'.", job_id, current_stage)
        emit_error(job_id, current_stage, str(exc))
        update_job(
            job.id,
            status="failed",
            failed_stage=current_stage,
            error_message=str(exc),
            retry_count=self.request.retries,
        )
        raise

    # ---------------------------------------------------------------------- #
    # Guaranteed cleanup regardless of outcome
    # ---------------------------------------------------------------------- #
    finally:
        _cleanup_temp_dir(temp_dir, job_id)
        
        # Emit webhook for job failure (if status is "failed")
        try:
            updated_job = get_job(job_id)
            if updated_job and updated_job.user_id and updated_job.status == "failed":
                emit_job_completed(
                    job_id=job_id,
                    user_id=updated_job.user_id,
                    status="failed",
                    clips_count=0,
                    cost_usd=round(float(updated_job.actual_cost_usd), 6),
                )
        except Exception as exc:
            logger.error("[job=%s] Failed to emit failure webhook: %s", job_id, exc)
