from __future__ import annotations

import json
import subprocess
from pathlib import Path


def _run_command(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, text=True)


def get_video_duration_seconds(video_path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def extract_audio(video_path: Path, output_audio_path: Path) -> Path:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "mp3",
        "-q:a",
        "2",
        str(output_audio_path),
    ]
    _run_command(command)
    return output_audio_path


def cut_clip(video_path: Path, start_time: float, end_time: float, output_path: Path) -> Path:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-ss",
        str(start_time),
        "-to",
        str(end_time),
        "-c",
        "copy",
        str(output_path),
    ]
    _run_command(command)
    return output_path


def build_subtitle_filter(srt_path: Path) -> str:
    subtitle_path = srt_path.resolve().as_posix().replace(":", r"\:")
    return (
        "crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale=1080:1920,"
        f"subtitles={subtitle_path}:force_style='FontName=Arial,FontSize=22,Bold=1,"
        "Alignment=2,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2'"
    )


def render_vertical_captioned_clip(
    raw_clip_path: Path,
    srt_path: Path,
    output_path: Path,
) -> Path:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(raw_clip_path),
        "-vf",
        build_subtitle_filter(srt_path),
        "-c:v",
        "libx264",
        "-crf",
        "23",
        "-preset",
        "fast",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(output_path),
    ]
    _run_command(command)
    return output_path
