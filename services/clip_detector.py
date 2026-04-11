from __future__ import annotations

import json
from pathlib import Path

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from services.caption_renderer import flatten_words
from services.cost_tracker import estimate_llm_cost_from_tokens


def _timestamp_label(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02}:{secs:02}"


def calculate_final_score(candidate: dict) -> float:
    return round(
        (float(candidate["hook_score"]) * 0.30)
        + (float(candidate["emotion_score"]) * 0.25)
        + (float(candidate["clarity_score"]) * 0.20)
        + (float(candidate["story_score"]) * 0.15)
        + (float(candidate["virality_score"]) * 0.10),
        2,
    )


def format_transcript_chunk(words: list[dict], words_per_line: int = 12) -> str:
    lines: list[str] = []
    for index in range(0, len(words), words_per_line):
        chunk = words[index : index + words_per_line]
        if not chunk:
            continue
        timestamp = _timestamp_label(float(chunk[0]["start"]))
        text = " ".join(word["word"].strip() for word in chunk).strip()
        lines.append(f"[{timestamp}] {text}")
    return "\n".join(lines)


def chunk_transcript(words: list[dict]) -> list[list[dict]]:
    if not words:
        return []

    chunk_size = settings.transcript_chunk_minutes * 60
    overlap = settings.transcript_chunk_overlap_seconds
    chunks: list[list[dict]] = []
    start_time = 0.0
    end_of_transcript = float(words[-1]["end"])

    while start_time <= end_of_transcript:
        end_time = start_time + chunk_size
        chunk_words = [
            word
            for word in words
            if float(word["end"]) >= start_time and float(word["start"]) <= end_time
        ]
        if chunk_words:
            chunks.append(chunk_words)
        if end_time >= end_of_transcript:
            break
        start_time += chunk_size - overlap

    return chunks


def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    deduped: dict[tuple[int, int], dict] = {}
    for candidate in candidates:
        key = (
            round(float(candidate["start_time"]) * 10),
            round(float(candidate["end_time"]) * 10),
        )
        if key not in deduped or float(candidate["final_score"]) > float(
            deduped[key]["final_score"]
        ):
            deduped[key] = candidate
    return list(deduped.values())


def select_top_clips(candidates: list[dict], limit: int = 3) -> list[dict]:
    selected: list[dict] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (float(item["final_score"]), float(item["hook_score"])),
        reverse=True,
    ):
        overlaps = any(
            not (
                float(candidate["end_time"]) <= float(existing["start_time"])
                or float(candidate["start_time"]) >= float(existing["end_time"])
            )
            for existing in selected
        )
        if overlaps:
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


class ClipDetectorService:
    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for clip detection")
        self.client = OpenAI(api_key=settings.openai_api_key)

    def load_prompt(self, prompt_version: str) -> str:
        path = Path(__file__).resolve().parent.parent / "prompts" / f"clip_detection_{prompt_version}.txt"
        return path.read_text(encoding="utf-8")

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    )
    def score_chunk(self, rendered_prompt: str) -> tuple[list[dict], float]:
        response = self.client.chat.completions.create(
            model=settings.clip_detector_model,
            temperature=0.2,
            messages=[{"role": "user", "content": rendered_prompt}],
        )
        content = response.choices[0].message.content or "[]"
        candidates = json.loads(content)
        usage = getattr(response, "usage", None)
        llm_cost = estimate_llm_cost_from_tokens(
            settings.clip_detector_model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return candidates, llm_cost

    def detect_clips(self, transcript_json: dict, prompt_version: str) -> tuple[list[dict], float]:
        prompt_template = self.load_prompt(prompt_version)
        all_candidates: list[dict] = []
        total_cost = 0.0
        words = flatten_words(transcript_json)

        for chunk_words in chunk_transcript(words):
            transcript_chunk = format_transcript_chunk(chunk_words)
            rendered_prompt = prompt_template.replace("{transcript_chunk}", transcript_chunk)
            candidates, chunk_cost = self.score_chunk(rendered_prompt)
            total_cost += chunk_cost
            for candidate in candidates:
                duration = float(candidate["end_time"]) - float(candidate["start_time"])
                if duration < settings.min_clip_length_seconds or duration > settings.max_clip_length_seconds:
                    continue
                candidate["duration"] = round(duration, 2)
                candidate["final_score"] = calculate_final_score(candidate)
                if float(candidate["final_score"]) < 6.5:
                    continue
                all_candidates.append(candidate)

        deduped = dedupe_candidates(all_candidates)
        selected = select_top_clips(deduped, limit=3)

        results: list[dict] = []
        for index, candidate in enumerate(selected, start=1):
            results.append(
                {
                    "clip_index": index,
                    "start_time": float(candidate["start_time"]),
                    "end_time": float(candidate["end_time"]),
                    "duration": float(candidate["duration"]),
                    "clip_url": "",
                    "hook_score": float(candidate["hook_score"]),
                    "emotion_score": float(candidate["emotion_score"]),
                    "clarity_score": float(candidate["clarity_score"]),
                    "story_score": float(candidate["story_score"]),
                    "virality_score": float(candidate["virality_score"]),
                    "final_score": float(candidate["final_score"]),
                    "reason": str(candidate["reason"]),
                }
            )

        return results, round(total_cost, 6)


def get_clip_detector_service() -> ClipDetectorService:
    return ClipDetectorService()
