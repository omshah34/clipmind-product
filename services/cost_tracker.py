"""File: services/cost_tracker.py
Purpose: Calculates estimated cost before processing and accumulates actual API
         cost after calls. Tracks per-job costs for billing implementation.
"""

from __future__ import annotations

import math

from core.config import settings


DEFAULT_LLM_COST_PER_CHUNK = 0.01
MODEL_PRICING_PER_MILLION = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "meta-llama/llama-4-scout-17b-16e-instruct": {"input": 0.11, "output": 0.34},
    "qwen/qwen3-32b": {"input": 0.29, "output": 0.59},
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
    "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
}
WHISPER_COST_PER_HOUR = {
    "whisper-large-v3": 0.111,
    "whisper-large-v3-turbo": 0.04,
}


def estimate_whisper_cost(duration_seconds: float) -> float:
    hourly_rate = WHISPER_COST_PER_HOUR.get(settings.whisper_model, WHISPER_COST_PER_HOUR["whisper-large-v3"])
    return round((duration_seconds / 3600.0) * hourly_rate, 6)


def estimate_chunk_count(duration_seconds: float) -> int:
    chunk_seconds = settings.transcript_chunk_minutes * 60
    overlap_seconds = settings.transcript_chunk_overlap_seconds
    if duration_seconds <= 0:
        return 0
    if duration_seconds <= chunk_seconds:
        return 1

    step = chunk_seconds - overlap_seconds
    chunks = 1 + math.ceil((duration_seconds - chunk_seconds) / step)
    return max(chunks, 1)


def estimate_job_cost(duration_seconds: float) -> float:
    whisper_cost = estimate_whisper_cost(duration_seconds)
    llm_cost = estimate_chunk_count(duration_seconds) * DEFAULT_LLM_COST_PER_CHUNK
    return round(whisper_cost + llm_cost, 6)


def estimate_llm_cost_from_tokens(
    model_name: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float:
    pricing = MODEL_PRICING_PER_MILLION.get(model_name)
    if not pricing or prompt_tokens is None or completion_tokens is None:
        return 0.0

    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)
