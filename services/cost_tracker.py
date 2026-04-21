"""File: services/cost_tracker.py
Purpose: Calculates estimated cost before processing and accumulates actual API
         cost after calls. Tracks per-job costs for billing implementation.
"""

from __future__ import annotations

import math

from core.config import settings


WHISPER_COST_PER_MINUTE = 0.006
DEFAULT_LLM_COST_PER_CHUNK = 0.01
MODEL_PRICING_PER_MILLION = {
    "gpt-4o": {"input": 5.0, "output": 15.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
}


def estimate_whisper_cost(duration_seconds: float) -> float:
    return round((duration_seconds / 60.0) * WHISPER_COST_PER_MINUTE, 6)


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
