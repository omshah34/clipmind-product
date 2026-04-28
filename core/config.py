"""File: config.py
Purpose: Load and manage all environment variables and application settings.
         Centralizes configuration from codex_identity.md including upload limits,
         chunk settings, polling interval, and API credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _default_clip_detector_fallback_model() -> str:
    base_url = os.getenv("OPENAI_BASE_URL", "").lower()
    if "integrate.api.nvidia.com" in base_url:
        return "openai/gpt-oss-20b"
    return "gpt-4o-mini"


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("ENVIRONMENT", "development")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "")  # Custom base URL (e.g. NVIDIA, OpenRouter)
    whisper_api_key: str = os.getenv("WHISPER_API_KEY", "")
    whisper_base_url: str = os.getenv("WHISPER_BASE_URL", "")
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis_socket_timeout: int = _get_int("REDIS_SOCKET_TIMEOUT", 30)
    redis_socket_connect_timeout: int = _get_int("REDIS_SOCKET_CONNECT_TIMEOUT", 30)
    storage_upload_timeout_seconds: int = _get_int("STORAGE_UPLOAD_TIMEOUT_SECONDS", 120)
    storage_download_timeout_seconds: int = _get_int("STORAGE_DOWNLOAD_TIMEOUT_SECONDS", 60)
    database_url: str = os.getenv("DATABASE_URL", "")
    frontend_url: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
    storage_bucket: str = os.getenv("STORAGE_BUCKET", "clipmind-videos")
    clip_prompt_version: str = os.getenv("CLIP_PROMPT_VERSION", "v4")
    max_upload_size_mb: int = _get_int("MAX_UPLOAD_SIZE_MB", 2048)
    max_video_duration_minutes: int = _get_int("MAX_VIDEO_DURATION_MINUTES", 90)
    transcript_chunk_minutes: int = _get_int("TRANSCRIPT_CHUNK_MINUTES", 5)
    transcript_chunk_overlap_seconds: int = _get_int(
        "TRANSCRIPT_CHUNK_OVERLAP_SECONDS", 60
    )
    polling_interval_seconds: int = _get_int("POLLING_INTERVAL_SECONDS", 4)
    poller_max_workers: int = _get_int("POLLER_MAX_WORKERS", 5)
    dev_mock_user_id: str = "00000000-0000-0000-0000-000000000000"

    # Phase 7: Security & Platform Auth
    fernet_key: str = os.getenv("FERNET_KEY", "")
    youtube_client_id: str = os.getenv("YOUTUBE_CLIENT_ID", "")
    youtube_client_secret: str = os.getenv("YOUTUBE_CLIENT_SECRET", "")
    tiktok_session_id: str = os.getenv("TIKTOK_SESSION_ID", "")
    ytdlp_cookies_file: str | None = os.getenv("YTDLP_COOKIES_FILE")
    
    # Webhook Secrets
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    youtube_webhook_secret: str = os.getenv("YOUTUBE_WEBHOOK_SECRET", "")

    min_video_duration_minutes: int = 2
    min_clip_length_seconds: int = _get_int("MIN_CLIP_LENGTH_SECONDS", 15)
    max_clip_length_seconds: int = _get_int("MAX_CLIP_LENGTH_SECONDS", 90)
    clip_detector_model: str = os.getenv("CLIP_DETECTOR_MODEL", "openai/gpt-oss-120b")
    clip_detector_fallback_model: str = os.getenv("CLIP_DETECTOR_FALLBACK_MODEL", _default_clip_detector_fallback_model())
    clip_detector_retry_attempts: int = _get_int("CLIP_DETECTOR_RETRY_ATTEMPTS", 1)
    openai_timeout_seconds: float = _get_float("OPENAI_TIMEOUT_SECONDS", 90.0)
    hf_token: str = os.getenv("HF_TOKEN", "")
    enable_contextual_broll: bool = _get_bool("ENABLE_CONTEXTUAL_BROLL", False)
    pexels_api_key: str = os.getenv("PEXELS_API_KEY", "")
    brand_guide_ocr_model: str = os.getenv("BRAND_GUIDE_OCR_MODEL", "gpt-4o-mini")
    whisper_model: str = "whisper-1"
    job_retry_limit: int = 3
    chunk_upload_size_bytes: int = 1024 * 1024
    feature_flag_prefix: str = os.getenv("FEATURE_FLAG_PREFIX", "CLIPMIND_FLAG_")
    request_context_header: str = os.getenv("REQUEST_ID_HEADER", "X-Request-ID")
    trace_context_header: str = os.getenv("TRACE_ID_HEADER", "X-Trace-ID")
    cdn_purge_url: str = os.getenv("CDN_PURGE_URL", "")
    cdn_purge_token: str = os.getenv("CDN_PURGE_TOKEN", "")
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
