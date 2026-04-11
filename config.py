from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/clipmind",
    )
    storage_bucket: str = os.getenv("STORAGE_BUCKET", "clipmind-videos")
    clip_prompt_version: str = os.getenv("CLIP_PROMPT_VERSION", "v1")
    max_upload_size_mb: int = _get_int("MAX_UPLOAD_SIZE_MB", 2048)
    max_video_duration_minutes: int = _get_int("MAX_VIDEO_DURATION_MINUTES", 90)
    transcript_chunk_minutes: int = _get_int("TRANSCRIPT_CHUNK_MINUTES", 5)
    transcript_chunk_overlap_seconds: int = _get_int(
        "TRANSCRIPT_CHUNK_OVERLAP_SECONDS", 60
    )
    polling_interval_seconds: int = _get_int("POLLING_INTERVAL_SECONDS", 4)

    min_video_duration_minutes: int = 2
    min_clip_length_seconds: int = 25
    max_clip_length_seconds: int = 60
    clip_detector_model: str = os.getenv("CLIP_DETECTOR_MODEL", "gpt-4o-mini")
    whisper_model: str = "whisper-1"
    job_retry_limit: int = 3
    chunk_upload_size_bytes: int = 1024 * 1024
    local_storage_dir: Path = BASE_DIR / ".clipmind_runtime" / "storage"
    temp_dir: Path = BASE_DIR / ".clipmind_runtime" / "tmp"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def max_video_duration_seconds(self) -> int:
        return self.max_video_duration_minutes * 60

    @property
    def min_video_duration_seconds(self) -> int:
        return self.min_video_duration_minutes * 60


settings = Settings()

for folder in (
    settings.local_storage_dir / "uploads",
    settings.local_storage_dir / "audio",
    settings.local_storage_dir / "clips",
    settings.temp_dir,
):
    folder.mkdir(parents=True, exist_ok=True)
