"""File: services/token_tracker.py
Purpose: Track AI token usage and calculate USD costs for all LLM calls.
         Enables granular per-job cost visibility.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Current model rates per 1M tokens (as of May 2026)
# Adjust these values based on provider pricing
MODEL_RATES = {
    "llama-3.3-70b-versatile": {"prompt": 0.59, "completion": 0.79},
    "llama-3.1-8b-instant":    {"prompt": 0.05, "completion": 0.08},
    "qwen3-32b":              {"prompt": 0.30, "completion": 0.40},
    "whisper-large-v3":       {"prompt": 0.0,  "completion": 0.0, "per_min": 0.006}, # Groq is often cheaper/free for whisper
}

def calculate_llm_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Calculate the cost of an LLM call in USD."""
    rates = MODEL_RATES.get(model, {"prompt": 0.5, "completion": 1.0}) # Default rates
    
    prompt_cost = (prompt_tokens / 1_000_000) * rates["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * rates["completion"]
    
    return round(prompt_cost + completion_cost, 6)

def extract_usage_from_response(response: Any) -> dict[str, int]:
    """Extract token usage from an OpenAI-compatible response object."""
    usage = getattr(response, "usage", None)
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0}
    
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", 0),
        "completion_tokens": getattr(usage, "completion_tokens", 0),
    }

def update_job_usage(job_id: str, prompt_tokens: int, completion_tokens: int, model: str):
    """
    Log token usage for a job. 
    Note: In a real implementation, this would likely increment counters 
    in Redis or a DB to avoid N+1 writes. For now, we provide the logic.
    """
    cost = calculate_llm_cost(model, prompt_tokens, completion_tokens)
    logger.info("Job %s usage update: +%d prompt, +%d completion tokens (cost: $%.6f)", 
                job_id, prompt_tokens, completion_tokens, cost)
    # Further integration with JobRepository.update_job would happen here.
