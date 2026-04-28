"""File: services/openai_client.py
Purpose: Shared OpenAI client factory.
         Reads OPENAI_API_KEY and OPENAI_BASE_URL from config so all services
         automatically use a custom endpoint (e.g. NVIDIA NIM, OpenRouter)
         without any per-service changes.

Usage:
    from services.openai_client import make_openai_client
    client = make_openai_client()
"""

from __future__ import annotations

from openai import OpenAI

from core.config import settings


def make_openai_client(for_whisper: bool = False) -> OpenAI:
    """Create an OpenAI client using settings from .env.

    - OPENAI_API_KEY  : your API key (required)
    - OPENAI_BASE_URL : custom base URL (optional, e.g. https://integrate.api.nvidia.com/v1)
    - CLIP_DETECTOR_MODEL: default model name (optional, e.g. openai/gpt-oss-120b)

    When OPENAI_BASE_URL is set, every chat.completions.create() call is routed
    to that endpoint instead of api.openai.com — no other code changes needed.
    """
    if for_whisper:
        api_key = settings.whisper_api_key or settings.openai_api_key
        base_url = settings.whisper_base_url
    else:
        api_key = settings.openai_api_key
        base_url = settings.openai_base_url

    kwargs: dict = {"api_key": api_key, "timeout": settings.openai_timeout_seconds}
    if base_url:
        kwargs["base_url"] = base_url
    elif for_whisper:
        # Prevent openai library from automatically reading OPENAI_BASE_URL from os.environ
        kwargs["base_url"] = "https://api.openai.com/v1"

    return OpenAI(**kwargs)
