from __future__ import annotations

from contextlib import ExitStack
import logging
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

import workers.pipeline as pipeline


class _AsyncExportEngine:
    async def generate_social_pulse(self, clip: dict) -> dict:
        return {
            "headlines": ["Generated headline"],
            "caption": "Generated caption",
            "hashtags": ["#tag"],
        }


class _FailingExportEngine:
    async def generate_social_pulse(self, clip: dict) -> dict:
        raise RuntimeError("social pulse unavailable")


class _TranscriptionService:
    def transcribe_audio(self, *args, **kwargs) -> tuple[dict, float]:
        return {
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.4},
                {"word": "world", "start": 0.4, "end": 0.8},
            ]
        }, 0.0


def test_completed_job_duplicate_task_is_not_warning(caplog) -> None:
    job_id = str(uuid4())
    job = SimpleNamespace(id=job_id, status="completed")

    with patch("workers.pipeline.get_job", return_value=job), caplog.at_level(logging.INFO):
        with pytest.raises(pipeline.Ignore):
            pipeline.process_job.run(job_id)

    assert "already completed; ignoring duplicate task" in caplog.text
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]


def _run_pipeline_with_render_metadata(export_engine, subject_tracker) -> tuple[dict[str, object], object]:
    job_id = str(uuid4())
    user_id = str(uuid4())
    captured: dict[str, object] = {}

    job = SimpleNamespace(
        id=job_id,
        status="uploaded",
        actual_cost_usd=0.0,
        source_video_url="file:///source.mp4",
        proxy_video_url=None,
        audio_url="file:///audio.mp3",
        transcript_json={
            "words": [
                {"word": "hello", "start": 0.0, "end": 0.4},
                {"word": "world", "start": 0.4, "end": 0.8},
            ]
        },
        brand_kit_id=None,
        prompt_version="v4",
        user_id=user_id,
        language="en",
    )

    def download_to_local(source_url: str, local_target: Path) -> Path:
        local_target.parent.mkdir(parents=True, exist_ok=True)
        local_target.write_bytes(b"placeholder")
        return local_target

    def upload_file(local_path: Path, folder: str, filename: str) -> str:
        return f"file:///{folder}/{filename}"

    def complete_job_atomic(job_id_value: str, clips: list[dict], actual_cost: float) -> None:
        captured["clips"] = clips
        captured["actual_cost"] = actual_cost

    def create_rendered_output(*args, **kwargs) -> None:
        output_path = Path(args[2])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"rendered")

    detected_clip = {
        "clip_index": 0,
        "start_time": 0.0,
        "end_time": 2.0,
        "duration": 2.0,
        "hook_score": 8.5,
        "emotion_score": 7.5,
        "clarity_score": 7.0,
        "story_score": 6.5,
        "virality_score": 8.0,
        "final_score": 7.8,
        "reason": "Strong demo segment",
        "hook_headlines": [],
    }

    with tempfile.TemporaryDirectory() as temp_dir, ExitStack() as stack:
        stack.enter_context(patch("workers.pipeline.get_job", return_value=job))
        stack.enter_context(patch("workers.pipeline.update_job"))
        stack.enter_context(patch("workers.pipeline.complete_job_atomic", side_effect=complete_job_atomic))
        stack.enter_context(patch("workers.pipeline.storage_service.download_to_local", side_effect=download_to_local))
        stack.enter_context(patch("workers.pipeline.storage_service.upload_file", side_effect=upload_file))
        stack.enter_context(patch("services.video_processor.get_video_dimensions", return_value=(1280, 720)))
        stack.enter_context(patch("workers.pipeline.extract_audio"))
        cut_clip_mock = stack.enter_context(patch("workers.pipeline.cut_clip"))
        stack.enter_context(patch("workers.pipeline.render_vertical_captioned_clip", side_effect=create_rendered_output))
        stack.enter_context(patch("workers.pipeline.write_clip_ass"))
        stack.enter_context(patch("workers.pipeline.AudioEngine.get_transients", return_value=[]))
        stack.enter_context(patch("workers.pipeline.VisualEngine.find_contextual_broll", return_value=[]))
        stack.enter_context(patch("workers.pipeline.emit_stage"))
        stack.enter_context(patch("workers.pipeline.emit_progress"))
        stack.enter_context(patch("workers.pipeline.emit_clip_scored"))
        stack.enter_context(patch("workers.pipeline.emit_clip_ready"))
        stack.enter_context(patch("workers.pipeline.emit_completed"))
        stack.enter_context(patch("workers.pipeline.emit_error"))
        stack.enter_context(patch("workers.pipeline.emit_job_completed"))
        stack.enter_context(patch("workers.pipeline.emit_clips_generated"))
        stack.enter_context(patch("workers.pipeline.get_transcription_service", return_value=_TranscriptionService()))
        stack.enter_context(
            patch(
                "workers.pipeline.get_clip_detector_service",
                return_value=SimpleNamespace(detect_clips=lambda *a, **k: ([detected_clip], 0.0)),
            )
        )
        stack.enter_context(
            patch("workers.pipeline.get_subject_tracker", return_value=subject_tracker)
        )
        stack.enter_context(patch("workers.pipeline.get_export_engine", return_value=export_engine))
        stack.enter_context(
            patch(
                "workers.pipeline.get_discovery_service",
                return_value=SimpleNamespace(add_job_to_index=lambda *a, **k: None),
            )
        )
        stack.enter_context(patch("workers.pipeline.tempfile.mkdtemp", return_value=temp_dir))
        pipeline.process_job.run(job_id)

    return captured, cut_clip_mock


def test_pipeline_persists_render_recipe_metadata() -> None:
    captured, cut_clip_mock = _run_pipeline_with_render_metadata(
        _AsyncExportEngine(),
        SimpleNamespace(
            analyze_subjects=lambda *a, **k: SimpleNamespace(
                centers=[640.0, 960.0], detected_face_count=1, primary_face_area_ratio=0.12
            )
        ),
    )

    assert "clips" in captured
    clip = captured["clips"][0]
    assert clip["layout_type"] == "vertical"
    assert clip["visual_mode"] == "face_cam"
    assert clip["selected_hook"] == "Generated headline"
    assert clip["srt_url"].endswith(".srt")
    assert clip["render_recipe"]["audio_profile"] == "loudnorm_i_-14"
    assert clip["render_recipe"]["caption_enabled"] is True
    cut_clip_mock.assert_called()


def test_pipeline_persists_render_recipe_metadata_when_enrichment_falls_back() -> None:
    captured, cut_clip_mock = _run_pipeline_with_render_metadata(
        _FailingExportEngine(),
        SimpleNamespace(analyze_subjects=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tracking unavailable"))),
    )

    assert "clips" in captured
    clip = captured["clips"][0]
    assert clip["layout_type"] == "screen_only"
    assert clip["visual_mode"] == "screen_demo"
    assert clip["selected_hook"] == "Strong demo segment"
    assert clip["srt_url"].endswith(".srt")
    assert clip["render_recipe"]["layout_type"] == "screen_only"
    assert clip["render_recipe"]["visual_mode"] == "screen_demo"
    assert clip["render_recipe"]["selected_hook"] == "Strong demo segment"
    assert clip["render_recipe"]["subject_centers"] == []
    cut_clip_mock.assert_called()
