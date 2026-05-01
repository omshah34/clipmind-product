"""File: services/openai_client.py
Purpose: Shared OpenAI client factory.
         Uses the OpenAI SDK against Groq's OpenAI-compatible API and provides
         a shared multi-model failover path for chat-based tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from openai import OpenAI
from openai import OpenAIError

from core.config import settings
from services.llm_config import get_llm_config, TaskType
from services.token_tracker import extract_usage_from_response, update_job_usage
from services.llm_cache import llm_cache

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatCompletionResult:
    model: str
    response: Any


_TEXT_FAILOVER_ERRORS = (
    OpenAIError,
    TimeoutError,
)


def make_openai_client(for_whisper: bool = False) -> OpenAI:
    """Create an OpenAI SDK client pointed at Groq's OpenAI-compatible API."""
    if for_whisper:
        api_key = settings.whisper_api_key or settings.groq_api_key
        base_url = settings.whisper_base_url or settings.groq_base_url
    else:
        api_key = settings.groq_api_key
        base_url = settings.groq_base_url

    kwargs: dict = {"api_key": api_key, "timeout": settings.openai_timeout_seconds}
    if base_url:
        kwargs["base_url"] = base_url

    return OpenAI(**kwargs)


def is_llm_available() -> bool:
    return bool(settings.groq_api_key)


def get_text_model_chain(preferred_model: str | None = None) -> list[str]:
    models = list(settings.groq_text_models)
    if preferred_model and preferred_model not in models:
        models.insert(0, preferred_model)
    elif preferred_model:
        models.remove(preferred_model)
        models.insert(0, preferred_model)
    return models


def get_vision_model_chain(preferred_model: str | None = None) -> list[str]:
    models = list(settings.groq_vision_models)
    if preferred_model and preferred_model not in models:
        models.insert(0, preferred_model)
    elif preferred_model:
        models.remove(preferred_model)
        models.insert(0, preferred_model)
    return models


def create_chat_completion(
    *,
    messages: list[dict[str, Any]],
    task_type: TaskType = TaskType.ANALYTICAL, # Gap 251
    job_id: str | None = None, # Gap 252
    preferred_model: str | None = None,
    vision: bool = False,
    client: OpenAI | None = None,
    **kwargs: Any,
) -> ChatCompletionResult:
    """Run a chat completion against Groq with ordered model failover."""
    if not is_llm_available():
        raise RuntimeError("GROQ_API_KEY is required for LLM tasks.")

    active_client = client or make_openai_client()
    model_chain = (
        get_vision_model_chain(preferred_model)
        if vision
        else get_text_model_chain(preferred_model)
    )

    # Gap 251: Task-specific configuration
    llm_cfg = get_llm_config(task_type)
    final_kwargs = {
        "temperature": llm_cfg.temperature,
        "max_tokens": llm_cfg.max_tokens,
        "top_p": llm_cfg.top_p,
        **kwargs
    }

    # Gap 253: Cache lookup
    cached_response = llm_cache.get(str(messages), model_chain[0], **final_kwargs)
    if cached_response:
        return ChatCompletionResult(model=model_chain[0], response=cached_response)

    errors: list[str] = []
    for attempt, model in enumerate(model_chain, start=1):
        try:
            response = active_client.chat.completions.create(
                model=model,
                messages=messages,
                **final_kwargs,
            )
            
            # Gap 252: Usage tracking
            if job_id:
                usage = extract_usage_from_response(response)
                update_job_usage(
                    job_id, 
                    usage["prompt_tokens"], 
                    usage["completion_tokens"], 
                    model
                )

            # Gap 253: Cache store
            llm_cache.set(str(messages), model, response, **final_kwargs)

            if attempt > 1:
                logger.info("Groq failover recovered with model '%s' on attempt %d.", model, attempt)
            return ChatCompletionResult(model=model, response=response)
        except _TEXT_FAILOVER_ERRORS as exc:
            status_code = getattr(exc, "status_code", None)
            status_text = f" status={status_code}" if status_code is not None else ""
            logger.warning(
                "Groq model '%s' failed on attempt %d/%d (%s%s). Trying next model.",
                model,
                attempt,
                len(model_chain),
                type(exc).__name__,
                status_text,
            )
            errors.append(f"{model}: {type(exc).__name__}({exc})")

    joined = " | ".join(errors) if errors else "no models attempted"
    raise RuntimeError(f"All Groq models failed. Attempts: {joined}")
