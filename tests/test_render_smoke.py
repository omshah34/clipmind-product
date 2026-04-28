from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from services.caption_renderer import write_ass_from_srt
from services.video_processor import render_vertical_captioned_clip


pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe are required for smoke render validation",
)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=True)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_ffmpeg_render_smoke() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source_path = root / "source.mp4"
        ass_path = root / "captions.ass"
        output_path = root / "output.mp4"
        top_frame_early = root / "top_early.png"
        top_frame_late = root / "top_late.png"

        _run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=blue:s=1280x720:d=3",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=1000:sample_rate=48000:d=3",
                "-shortest",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(source_path),
            ]
        )

        write_ass_from_srt(
            "1\n00:00:00,000 --> 00:00:02,000\nhello world\n",
            ass_path,
            preset_name="hormozi",
            layout_type="vertical",
        )

        render_vertical_captioned_clip(
            source_path,
            ass_path,
            output_path,
            headline="Hook overlay",
            render_recipe={
                "layout_type": "vertical",
                "subject_centers": [],
                "screen_focus": "center",
                "selected_hook": "Hook overlay",
                "caption_preset": "hormozi",
                "caption_enabled": True,
                "watermark_enabled": False,
                "audio_profile": "loudnorm_i_-14",
            },
        )

        probe = _run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_streams",
                "-of",
                "json",
                str(output_path),
            ]
        )
        streams = json.loads(probe.stdout)["streams"]
        video_stream = next(stream for stream in streams if stream["codec_type"] == "video")
        audio_streams = [stream for stream in streams if stream["codec_type"] == "audio"]

        assert video_stream["width"] == 1080
        assert video_stream["height"] == 1920
        assert audio_streams

        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "0.5",
                "-i",
                str(output_path),
                "-frames:v",
                "1",
                "-vf",
                "crop=1080:420:0:0",
                str(top_frame_early),
            ]
        )
        _run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                "1.8",
                "-i",
                str(output_path),
                "-frames:v",
                "1",
                "-vf",
                "crop=1080:420:0:0",
                str(top_frame_late),
            ]
        )

        assert _sha256(top_frame_early) != _sha256(top_frame_late)
