from __future__ import annotations

from pathlib import Path

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from services.caption_renderer import flatten_words
from services.cost_tracker import estimate_whisper_cost


class TranscriptionService:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for transcription")
        self.client = OpenAI(api_key=settings.openai_api_key)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    )
    def transcribe_audio(self, audio_path: Path) -> tuple[dict, float]:
        with audio_path.open("rb") as audio_file:
            response = self.client.audio.transcriptions.create(
                model=settings.whisper_model,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"],
            )

        transcript_json = (
            response.model_dump() if hasattr(response, "model_dump") else dict(response)
        )
        transcript_json["words"] = flatten_words(transcript_json)

        words = transcript_json["words"]
        duration_seconds = float(words[-1]["end"]) if words else 0.0
        return transcript_json, estimate_whisper_cost(duration_seconds)


def get_transcription_service() -> TranscriptionService:
    return TranscriptionService()
