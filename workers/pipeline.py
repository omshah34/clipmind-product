from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
from celery.exceptions import Ignore
from openai import APIConnectionError, APITimeoutError, RateLimitError

from config import settings
from db.queries import get_job, update_job
from services.caption_renderer import write_clip_srt
from services.clip_detector import get_clip_detector_service
from services.storage import storage_service
from services.transcription import get_transcription_service
from services.video_processor import cut_clip, extract_audio, render_vertical_captioned_clip
from workers.celery_app import celery_app


TRANSIENT_ERRORS = (httpx.TimeoutException, APIConnectionError, APITimeoutError, RateLimitError)


@celery_app.task(bind=True, name="workers.pipeline.process_job")
def process_job(self, job_id: str) -> list[dict]:
    job = get_job(job_id)
    if job is None:
        raise Ignore()

    current_stage = "queued"
    actual_cost = float(job.actual_cost_usd)
    transcription_service = get_transcription_service()
    clip_detector_service = get_clip_detector_service()

    try:
        update_job(
            job.id,
            status="queued",
            failed_stage=None,
            error_message=None,
            retry_count=self.request.retries,
        )

        with tempfile.TemporaryDirectory(prefix=f"clipmind_{job.id}_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            source_video_path = storage_service.download_to_local(
                job.source_video_url,
                str(job.id),
                ".mp4",
            )

            current_stage = "extracting_audio"
            update_job(job.id, status=current_stage)
            audio_path = temp_dir / f"{job.id}.mp3"
            extract_audio(source_video_path, audio_path)
            audio_url = storage_service.upload_file(audio_path, "audio", f"{job.id}.mp3")
            update_job(job.id, audio_url=audio_url)

            current_stage = "transcribing"
            update_job(job.id, status=current_stage)
            transcript_json, transcription_cost = transcription_service.transcribe_audio(audio_path)
            actual_cost += transcription_cost
            update_job(
                job.id,
                transcript_json=transcript_json,
                actual_cost_usd=round(actual_cost, 6),
            )

            current_stage = "detecting_clips"
            update_job(job.id, status=current_stage)
            detected_clips, llm_cost = clip_detector_service.detect_clips(
                transcript_json,
                prompt_version=job.prompt_version,
            )
            actual_cost += llm_cost

            if not detected_clips:
                update_job(
                    job.id,
                    status="completed",
                    clips_json=[],
                    actual_cost_usd=round(actual_cost, 6),
                )
                return []

            final_clips: list[dict] = []
            current_stage = "cutting_video"
            update_job(job.id, status=current_stage)
            for clip in detected_clips:
                clip_index = int(clip["clip_index"])
                raw_clip_path = temp_dir / f"clip_{clip_index}_raw.mp4"
                srt_path = temp_dir / f"clip_{clip_index}.srt"
                final_clip_path = temp_dir / f"clip_{clip_index}_final.mp4"

                cut_clip(
                    source_video_path,
                    start_time=float(clip["start_time"]),
                    end_time=float(clip["end_time"]),
                    output_path=raw_clip_path,
                )

                current_stage = "rendering_captions"
                update_job(job.id, status=current_stage)
                write_clip_srt(
                    transcript_json,
                    clip_start_time=float(clip["start_time"]),
                    clip_end_time=float(clip["end_time"]),
                    output_path=srt_path,
                )

                render_vertical_captioned_clip(raw_clip_path, srt_path, final_clip_path)

                current_stage = "exporting"
                update_job(job.id, status=current_stage)
                clip_url = storage_service.upload_file(
                    final_clip_path,
                    "clips",
                    f"{job.id}_clip_{clip_index}.mp4",
                )

                final_clip = dict(clip)
                final_clip["clip_url"] = clip_url
                final_clips.append(final_clip)

            update_job(
                job.id,
                status="completed",
                clips_json=final_clips,
                actual_cost_usd=round(actual_cost, 6),
                failed_stage=None,
                error_message=None,
            )
            return final_clips

    except TRANSIENT_ERRORS as exc:
        retry_count = self.request.retries + 1
        if retry_count <= settings.job_retry_limit:
            update_job(
                job.id,
                status="retrying",
                retry_count=retry_count,
                failed_stage=current_stage,
                error_message=str(exc),
            )
            raise self.retry(exc=exc, countdown=5 * retry_count)

        update_job(
            job.id,
            status="failed",
            retry_count=retry_count,
            failed_stage=current_stage,
            error_message=str(exc),
        )
        raise

    except Exception as exc:
        update_job(
            job.id,
            status="failed",
            failed_stage=current_stage,
            error_message=str(exc),
            retry_count=self.request.retries,
        )
        raise
