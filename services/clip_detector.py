"""File: services/clip_detector.py
Purpose: Transcript chunking, prompt loading, LLM scoring, overlap removal,
         thresholding, and final clip selection. Core AI scoring logic.

Improvements over v4:
  - chunk_transcript guards against stride_s <= 0 (overlap >= chunk size),
    which previously caused an infinite loop with no error message
  - SCORE_WEIGHTS sum validated at module load — silent weight misconfiguration
    can no longer corrupt every score across every job
  - Candidate dicts no longer mutated in-place inside detect_clips; a fresh
    dict is constructed via {**candidate, ...} so chunk_results stay clean
  - PromptTemplate.substitute() KeyError (unknown @@{variable} in prompt file)
    now re-raised as ClipDetectionError naming the file and the unknown key,
    rather than an opaque KeyError propagating to the pipeline
"""

from __future__ import annotations

import bisect
import hashlib
import json
import logging
import re
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from pathlib import Path
from string import Template
from typing import TypedDict, Any

from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.redis import get_redis_client
from services.caption_renderer import flatten_words
from services.cost_tracker import estimate_llm_cost_from_tokens
from services.content_dna import get_personalized_weights

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Weights must sum to 1.0. Adjust here — nowhere else.
#: The assertion below this block enforces the invariant at import time.
SCORE_WEIGHTS: dict[str, float] = {
    "hook_score":     0.30,
    "emotion_score":  0.25,
    "virality_score": 0.25,
    "clarity_score":  0.10,
    "story_score":    0.10,
}

# Fail loudly at import time rather than silently miscalculating every score.
assert abs(sum(SCORE_WEIGHTS.values()) - 1.0) < 1e-9, (
    f"SCORE_WEIGHTS must sum to 1.0, got {sum(SCORE_WEIGHTS.values()):.10f}. "
    "Adjust the weights so they sum to exactly 1.0."
)

#: Minimum acceptable final_score to keep a candidate.
SCORE_THRESHOLD: float = 5.5

#: Valid range for each individual dimension score from the LLM.
SCORE_MIN: float = 1.0
SCORE_MAX: float = 10.0

#: Required keys in every LLM candidate object.
CANDIDATE_REQUIRED_KEYS: frozenset[str] = frozenset(
    {*SCORE_WEIGHTS.keys(), "start_time", "end_time", "reason", "hook_headlines"}
)

#: Maximum threads for parallel chunk scoring.
MAX_SCORE_WORKERS: int = 4

#: Emit WARNING (rather than INFO) when this fraction of chunks fail scoring.
CHUNK_FAILURE_WARN_RATIO: float = 0.5


class ServiceMode(str, Enum):
    FULL = "full"        # AI scoring + all features
    DEGRADED = "degraded" # Basic extraction, no AI scores
    OFFLINE = "offline"  # Queue only, process later

DEGRADED_FLAG_KEY = "clipmind:degraded_mode"

def check_ai_health() -> ServiceMode:
    """Gap 363: Returns current service mode based on Redis circuit breaker."""
    try:
        redis = get_redis_client()
        mode = redis.get(DEGRADED_FLAG_KEY)
        if mode:
            return ServiceMode(mode.decode())
    except Exception as e:
        logger.error(f"Failed to check AI health from Redis: {e}")
    return ServiceMode.FULL

def enter_degraded_mode(reason: str, ttl: int = 300) -> None:
    """Gap 363: Trip degraded mode for ttl seconds."""
    try:
        redis = get_redis_client()
        redis.setex(DEGRADED_FLAG_KEY, ttl, ServiceMode.DEGRADED.value)
        logger.critical(f"🔴 DEGRADED MODE ACTIVATED: {reason} — expires in {ttl}s")
    except Exception as e:
        logger.error(f"Failed to set degraded mode in Redis: {e}")

def _is_provider_outage(e: Exception) -> bool:
    """Gap 363: Distinguish provider outage (degrade) from prompt errors (raise)."""
    msg = str(e).lower()
    return any(k in msg for k in ["502", "503", "504", "connection", "timeout", "overloaded", "unavailable"])


# ---------------------------------------------------------------------------
# Prompt templating
# ---------------------------------------------------------------------------

class PromptTemplate(Template):
    """Template subclass that uses '@@' as the delimiter instead of '$'.

    Standard string.Template raises ValueError on any bare '$' in the source
    text, which is common in prompt files (dollar amounts, shell examples,
    API cost examples). Using '@@' as the delimiter makes substitution safe
    regardless of prompt content.

    Prompt files must use @@{transcript_chunk} as the substitution placeholder.
    Any other @@{variable} in the file raises ClipDetectionError at render time
    with the filename and unknown key — not an opaque KeyError.
    """
    delimiter = "@@"


# ---------------------------------------------------------------------------
# Typed dicts
# ---------------------------------------------------------------------------

class RawCandidate(TypedDict):
    start_time: float
    end_time: float
    hook_score: float
    emotion_score: float
    clarity_score: float
    story_score: float
    virality_score: float
    reason: str
    hook_headlines: list[str]
    layout_suggestion: str


class ScoredClip(TypedDict):
    clip_index: int
    start_time: float
    end_time: float
    duration: float
    clip_url: str | None      # None at detection time; filled in by pipeline after upload
    hook_score: float
    emotion_score: float
    clarity_score: float
    story_score: float
    virality_score: float
    final_score: float
    reason: str
    hook_headlines: list[str]
    layout_suggestion: str
    refinement_reason: str | None
    score_source: str
    score_confidence: float


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ClipDetectionError(RuntimeError):
    """Raised when clip detection cannot proceed due to an unrecoverable error."""


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _timestamp_label(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{minutes:02}:{secs:02}"


def _coerce_float(value: object, field: str) -> float:
    """Coerce a raw LLM value to float, raising ClipDetectionError on failure."""
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise ClipDetectionError(
            f"Field '{field}' could not be converted to float: {value!r}"
        ) from exc


# Matches any JSON string value (handles escaped quotes inside strings).
# Used by _repair_json to neutralise structural chars inside string values.
_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"')


def _repair_json(raw: str) -> str:
    """Attempt light-touch repair of truncated or slightly malformed JSON arrays.

    Handles the most common LLM failure modes:
      1. Missing closing bracket/brace (truncated output).
      2. Trailing commas before ] or }.
      3. Non-JSON preamble before the first '['.

    Brace/bracket counting is performed on a copy with string values stripped
    so that structural characters inside "reason" or other text fields (e.g.
    `"great hook {loud music}"`) do not corrupt the repair output.
    """
    first_bracket = raw.find("[")
    if first_bracket == -1:
        return "[]"
    raw = raw[first_bracket:]

    # Remove trailing commas before closing delimiters
    raw = re.sub(r",\s*([}\]])", r"\1", raw)

    # Count structural characters on a string-stripped copy to avoid
    # being fooled by { or [ appearing inside quoted string values
    stripped = _JSON_STRING_RE.sub('""', raw)
    opens = stripped.count("{") - stripped.count("}")
    closes = stripped.count("[") - stripped.count("]")

    if opens > 0 or closes > 0:
        raw = raw.rstrip().rstrip(",")
        raw += "}" * opens + "]" * closes

    return raw


# ---------------------------------------------------------------------------
# Scoring functions
# ---------------------------------------------------------------------------

def validate_and_coerce_scores(candidate: dict) -> dict[str, float]:
    """Coerce and validate all dimension scores in one pass.

    Returns a dict of {score_key: coerced_float} so callers never re-coerce.
    Raises ClipDetectionError if any score is out of the valid range.
    """
    # Required keys for candidate validation
    required_keys = {*SCORE_WEIGHTS.keys(), "start_time", "end_time", "reason", "hook_headlines", "layout_suggestion"}
    missing = required_keys - candidate.keys()
    if missing:
        raise ClipDetectionError(f"Candidate missing keys: {missing}")

    coerced: dict[str, float] = {}
    for key in SCORE_WEIGHTS:
        value = _coerce_float(candidate.get(key), key)
        if not (SCORE_MIN <= value <= SCORE_MAX):
            raise ClipDetectionError(
                f"Score '{key}' = {value} is out of valid range "
                f"[{SCORE_MIN}, {SCORE_MAX}]"
            )
        coerced[key] = value
    return coerced


def calculate_final_score(coerced_scores: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Compute the weighted final score from pre-coerced dimension scores.
    
    Args:
        coerced_scores: Individual dimension scores (hook, emotion, etc.)
        weights: Custom weights dict. If None, uses default SCORE_WEIGHTS.
    
    Returns:
        Weighted final score (0-10 scale)
    """
    if weights is None:
        weights = SCORE_WEIGHTS
    
    return round(
        sum(coerced_scores[key] * weight for key, weight in weights.items()),
        2,
    )


def normalize_score_weights(weights: dict[str, float] | None) -> dict[str, float]:
    """Return scorer weights keyed by score field names and normalized to 1.0.

    Content DNA stores multiplier-style keys such as ``hook_weight`` while the
    detector scores use ``hook_score``. Apply those multipliers to the base
    detector weights, then normalize.
    """
    if not weights:
        return SCORE_WEIGHTS

    normalized: dict[str, float] = {}
    for score_key, base_weight in SCORE_WEIGHTS.items():
        weight_key = score_key.replace("_score", "_weight")
        if score_key in weights:
            normalized[score_key] = float(weights[score_key])
        elif weight_key in weights:
            normalized[score_key] = base_weight * float(weights[weight_key])
        else:
            normalized[score_key] = base_weight

    total = sum(normalized.values())
    if total <= 0:
        return SCORE_WEIGHTS
    return {key: value / total for key, value in normalized.items()}


# ---------------------------------------------------------------------------
# Transcript formatting
# ---------------------------------------------------------------------------

_WORDS_PER_LINE: int = 12


def format_transcript_chunk(words: list[dict], words_per_line: int = _WORDS_PER_LINE) -> str:
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
    """Split a flat word list into overlapping chunks for LLM scoring.

    Uses bisect on precomputed float arrays for O(log n) boundary finding.
    The loop is driven by an integer chunk_number so there is no cumulative
    float arithmetic and therefore no timestamp drift on long transcripts.

    Raises:
        ClipDetectionError: If overlap_seconds >= chunk_size_seconds, which
            would produce a non-positive stride and an infinite loop.
    """
    if not words:
        return []

    chunk_size_s = settings.transcript_chunk_minutes * 60
    overlap_s = settings.transcript_chunk_overlap_seconds
    stride_s = chunk_size_s - overlap_s

    # Guard: non-positive stride causes an infinite loop. Fail fast with a
    # clear message so the operator fixes settings rather than hanging forever.
    if stride_s <= 0:
        raise ClipDetectionError(
            f"transcript_chunk_overlap_seconds ({overlap_s}s) must be less than "
            f"transcript_chunk_minutes * 60 ({chunk_size_s}s). "
            f"Current stride would be {stride_s}s, causing an infinite loop."
        )

    starts: list[float] = [float(w["start"]) for w in words]
    ends: list[float] = [float(w["end"]) for w in words]
    total_end = ends[-1]

    chunks: list[list[dict]] = []
    chunk_number = 0  # integer loop driver — no float accumulation

    while True:
        window_start = chunk_number * stride_s
        window_end = window_start + chunk_size_s

        if window_start > total_end:
            break

        # First word whose end >= window_start
        lo = bisect.bisect_left(ends, window_start)
        # First word whose start > window_end
        hi = bisect.bisect_right(starts, window_end)

        chunk_words = words[lo:hi]
        if chunk_words:
            chunks.append(chunk_words)

        if window_end >= total_end:
            break

        chunk_number += 1

    return chunks


_HOOK_WORDS = {
    "how", "why", "what", "stop", "never", "always", "biggest", "secret",
    "truth", "mistake", "wrong", "fast", "best", "worst", "wait", "listen",
}
_EMOTION_WORDS = {
    "love", "hate", "afraid", "fear", "shocking", "crazy", "amazing", "incredible",
    "angry", "excited", "embarrassing", "painful", "surprised", "beautiful",
}
_TRANSITION_WORDS = {
    "then", "because", "finally", "suddenly", "after", "before", "but", "so",
    "therefore", "instead", "meanwhile", "first", "second", "next", "when",
}
_FILLER_WORDS = {
    "um", "uh", "like", "you know", "actually", "basically", "literally", "kind of",
}
_SECOND_PERSON_WORDS = {"you", "your", "you're", "youve", "you'll"}
_FIRST_PERSON_WORDS = {"i", "im", "i'm", "ive", "i've", "my", "me", "we", "our", "us"}


def _clamp_score(value: float, minimum: float = 4.8, maximum: float = 8.9) -> float:
    return round(max(minimum, min(maximum, value)), 2)


def _normalize_token(token: str) -> str:
    return re.sub(r"[^a-z0-9']", "", token.lower())


def _signal_ratio(tokens: list[str], lexicon: set[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for token in tokens if token in lexicon) / len(tokens)


def _deterministic_jitter(seed: str, scale: float = 0.18) -> float:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    unit = int(digest[:8], 16) / 0xFFFFFFFF
    return (unit - 0.5) * scale


def _generate_heuristic_headlines(words: list[dict], start_idx: int) -> list[str]:
    opening = [str(w.get("word", "")).strip(" ,.!?") for w in words[start_idx : start_idx + 8] if str(w.get("word", "")).strip()]
    snippet = " ".join(opening[:5]).strip()
    if not snippet:
        snippet = "Unexpected turning point"
    snippet = snippet[:60]
    return [
        snippet,
        f"Why {snippet[:40]}".strip(),
        f"Watch what happens next",
    ]


def _score_heuristic_candidate(
    segment_words: list[dict],
    *,
    start_time: float,
    end_time: float,
    total_end: float,
) -> dict[str, float]:
    tokens_raw = [str(word.get("word", "")).strip() for word in segment_words if str(word.get("word", "")).strip()]
    tokens = [_normalize_token(token) for token in tokens_raw]
    tokens = [token for token in tokens if token]
    token_count = len(tokens) or 1
    duration = max(end_time - start_time, 0.1)

    opening_tokens = tokens[:8]
    opening_raw = tokens_raw[:8]
    hook_density = _signal_ratio(opening_tokens, _HOOK_WORDS)
    emotion_density = _signal_ratio(tokens, _EMOTION_WORDS)
    transition_density = _signal_ratio(tokens, _TRANSITION_WORDS)
    second_person_density = _signal_ratio(tokens, _SECOND_PERSON_WORDS)
    first_person_density = _signal_ratio(tokens, _FIRST_PERSON_WORDS)
    filler_density = _signal_ratio(tokens, _FILLER_WORDS)
    question_bonus = 1.0 if any(token.endswith("?") for token in opening_raw) else 0.0
    exclaim_bonus = 1.0 if any(token.endswith("!") for token in tokens_raw) else 0.0
    number_bonus = min(sum(any(ch.isdigit() for ch in token) for token in opening_raw) / 2.0, 1.0)
    unique_ratio = len(set(tokens)) / token_count
    avg_word_len = sum(len(token) for token in tokens) / token_count
    long_word_ratio = min(avg_word_len / 7.0, 1.0)
    sentence_boundary_bonus = 1.0 if str(segment_words[-1].get("word", "")).strip().endswith((".", "?", "!")) else 0.0
    duration_signal = 1.0 - min(abs(duration - 45.0) / 35.0, 1.0)
    position_signal = 1.0 - min(start_time / max(total_end, 1.0), 1.0)
    mid_arc_signal = 1.0 - min(abs((start_time + end_time) / 2 - (total_end / 2)) / max(total_end / 2, 1.0), 1.0)
    contrast_bonus = 1.0 if {"but", "however"} & set(tokens) else 0.0

    seed = f"{round(start_time, 2)}:{round(end_time, 2)}:{' '.join(opening_tokens[:4])}"
    hook_score = _clamp_score(
        5.25
        + 2.3 * hook_density
        + 0.75 * question_bonus
        + 0.55 * number_bonus
        + 0.45 * second_person_density
        + 0.35 * position_signal
        + _deterministic_jitter(seed + ":hook")
    )
    emotion_score = _clamp_score(
        5.1
        + 2.1 * emotion_density
        + 0.7 * exclaim_bonus
        + 0.35 * first_person_density
        + 0.4 * contrast_bonus
        + _deterministic_jitter(seed + ":emotion")
    )
    clarity_score = _clamp_score(
        5.45
        + 1.35 * unique_ratio
        + 0.55 * long_word_ratio
        + 0.35 * sentence_boundary_bonus
        - 1.65 * filler_density
        + _deterministic_jitter(seed + ":clarity")
    )
    story_score = _clamp_score(
        5.0
        + 1.75 * transition_density
        + 0.7 * duration_signal
        + 0.55 * sentence_boundary_bonus
        + 0.45 * mid_arc_signal
        + _deterministic_jitter(seed + ":story")
    )
    virality_score = _clamp_score(
        5.0
        + 1.15 * hook_density
        + 0.9 * emotion_density
        + 0.65 * second_person_density
        + 0.55 * number_bonus
        + 0.35 * question_bonus
        + _deterministic_jitter(seed + ":virality")
    )

    return {
        "hook_score": hook_score,
        "emotion_score": emotion_score,
        "clarity_score": clarity_score,
        "story_score": story_score,
        "virality_score": virality_score,
    }


def estimate_heuristic_scores_for_range(
    words: list[dict],
    *,
    start_time: float,
    end_time: float,
) -> dict[str, float]:
    """Estimate fallback score dimensions for a specific clip span."""
    if not words:
        return {
            "hook_score": 5.5,
            "emotion_score": 5.2,
            "clarity_score": 5.8,
            "story_score": 5.1,
            "virality_score": 5.4,
        }

    total_end = float(words[-1]["end"])
    segment_words = [
        word for word in words
        if float(word.get("end", 0.0)) >= start_time and float(word.get("start", 0.0)) <= end_time
    ]
    if not segment_words:
        segment_words = words[: min(len(words), 20)]

    return _score_heuristic_candidate(
        segment_words,
        start_time=start_time,
        end_time=end_time,
        total_end=total_end,
    )


def build_heuristic_candidates(words: list[dict], limit: int = 5) -> list[dict]:
    """Generate usable fallback candidates when LLM scoring fails or times out."""
    if not words:
        return []

    starts = [float(w["start"]) for w in words]
    total_end = float(words[-1]["end"])
    if total_end < settings.min_clip_length_seconds:
        return []

    target_duration = min(60.0, max(35.0, settings.min_clip_length_seconds + 20.0))
    spacing = max(target_duration + 20.0, total_end / max(limit, 1))
    candidates: list[dict] = []

    for index in range(limit):
        target_start = index * spacing
        if target_start >= total_end - settings.min_clip_length_seconds:
            break

        start_idx = bisect.bisect_left(starts, target_start)
        start_idx = min(start_idx, len(words) - 1)

        target_end = min(total_end, starts[start_idx] + target_duration)
        end_idx = bisect.bisect_left(starts, target_end)
        end_idx = min(max(end_idx, start_idx + 1), len(words) - 1)

        # Snap end forward to a nearby sentence boundary when possible.
        max_end_time = min(total_end, starts[start_idx] + settings.max_clip_length_seconds)
        for i in range(end_idx, min(len(words), end_idx + 80)):
            token = str(words[i].get("word", "")).strip()
            if float(words[i]["end"]) > max_end_time:
                break
            if token.endswith((".", "?", "!")):
                end_idx = i
                break

        start_time = float(words[start_idx]["start"])
        end_time = float(words[end_idx]["end"])
        duration = end_time - start_time
        if not (settings.min_clip_length_seconds <= duration <= settings.max_clip_length_seconds):
            continue

        segment_words = words[start_idx : end_idx + 1]
        scores = _score_heuristic_candidate(
            segment_words,
            start_time=start_time,
            end_time=end_time,
            total_end=total_end,
        )
        opening_words = " ".join(str(w.get("word", "")).strip() for w in words[start_idx : start_idx + 10]).strip()
        candidates.append(
            {
                "source": "heuristic",
                "start_time": round(start_time, 2),
                "end_time": round(end_time, 2),
                **scores,
                "reason": f"Fallback candidate beginning with '{opening_words}' selected after LLM clip detection failed; scores were estimated from transcript structure and hook signals.",
                "hook_headlines": _generate_heuristic_headlines(words, start_idx),
                "layout_suggestion": "vertical",
                "score_confidence": 0.38,
            }
        )

    return candidates


# ---------------------------------------------------------------------------
# Deduplication & selection
# ---------------------------------------------------------------------------

def dedupe_candidates(candidates: list[dict]) -> list[dict]:
    """Collapse candidates with near-identical timestamps, keeping highest score."""
    deduped: dict[tuple[int, int], dict] = {}
    for candidate in candidates:
        key = (
            round(float(candidate["start_time"]) * 10),
            round(float(candidate["end_time"]) * 10),
        )
        existing = deduped.get(key)
        if existing is None or float(candidate["final_score"]) > float(existing["final_score"]):
            deduped[key] = candidate
    return list(deduped.values())


def select_top_clips(candidates: list[dict], limit: int = 3) -> list[dict]:
    """Select up to `limit` non-overlapping clips sorted by final_score desc."""
    selected: list[dict] = []
    for candidate in sorted(
        candidates,
        key=lambda c: (float(c["final_score"]), float(c["hook_score"])),
        reverse=True,
    ):
        c_start = float(candidate["start_time"])
        c_end = float(candidate["end_time"])
        overlaps = any(
            not (c_end <= float(e["start_time"]) or c_start >= float(e["end_time"]))
            for e in selected
        )
        if overlaps:
            continue
        selected.append(candidate)
        if len(selected) == limit:
            break
    return selected


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

@lru_cache(maxsize=8)
def _load_prompt_cached(path: str) -> PromptTemplate:
    """Load, parse, and cache a PromptTemplate. Keyed by resolved path string."""
    raw = Path(path).read_text(encoding="utf-8")
    raw = raw.replace("{{transcript_chunk}}", "@@{transcript_chunk}")
    return PromptTemplate(raw)


def _render_prompt(template: PromptTemplate, transcript_chunk: str, source_path: str) -> str:
    """Render a PromptTemplate, converting KeyError into a readable ClipDetectionError."""
    try:
        return template.substitute(transcript_chunk=transcript_chunk)
    except KeyError as exc:
        raise ClipDetectionError(
            f"Prompt file '{source_path}' contains unknown placeholder @@{{{exc.args[0]}}}. "
            "Only @@{transcript_chunk} is supported."
        ) from exc


class ClipDetectorService:
    def __init__(self) -> None:
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required for clip detection")
        from services.openai_client import make_openai_client
        self.client = make_openai_client()

    def load_prompt(self, prompt_version: str) -> tuple[PromptTemplate, str]:
        prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
        path = prompts_dir / f"clip_detection_{prompt_version}.txt"
        if not path.exists():
            fallback_path = prompts_dir / "clip_detection_v4.txt"
            if fallback_path.exists():
                logger.info(
                    "Prompt version %s not found at %s; falling back to %s",
                    prompt_version,
                    path,
                    fallback_path,
                )
                path = fallback_path
            else:
                raise FileNotFoundError(f"Prompt file not found: {path}")
        resolved = str(path)
        return _load_prompt_cached(resolved), resolved

    def _call_llm(self, prompt: str, model: str) -> tuple[str, Any]:
        """Low-level LLM call."""
        from services.openai_client import create_chat_completion

        result = create_chat_completion(
            client=self.client,
            preferred_model=model,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        response = result.response
        return response.choices[0].message.content or "[]", result

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.clip_detector_retry_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    )
    def score_chunk(self, rendered_prompt: str, model_override: str | None = None) -> tuple[list[dict], float]:
        """Call the LLM, parse candidates, and return (candidates, cost)."""
        model = model_override or settings.clip_detector_model
        raw_content, completion = self._call_llm(rendered_prompt, model)
        response = completion.response

        # Parse — attempt repair on failure
        try:
            candidates = json.loads(raw_content)
        except json.JSONDecodeError:
            logger.warning("LLM returned malformed JSON; attempting repair.")
            try:
                candidates = json.loads(_repair_json(raw_content))
            except json.JSONDecodeError:
                logger.error("JSON repair failed. Raw output:\n%s", raw_content[:500])
                candidates = []

        if isinstance(candidates, dict):
            for key in ("clips", "candidates", "results"):
                nested = candidates.get(key)
                if isinstance(nested, list):
                    candidates = nested
                    break

        if not isinstance(candidates, list):
            logger.warning("LLM response was not a JSON array; skipping chunk.")
            candidates = []

        valid: list[dict] = []
        for i, candidate in enumerate(candidates):
            try:
                coerced = validate_and_coerce_scores(candidate)
                valid.append({**candidate, **coerced})
            except ClipDetectionError as exc:
                logger.warning("Candidate %d failed validation: %s; skipping.", i, exc)
                continue

        usage = getattr(response, "usage", None)
        llm_cost = estimate_llm_cost_from_tokens(
            completion.model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

        logger.debug("Chunk scored (%s): %d valid, cost=$%.6f", completion.model, len(valid), llm_cost)
        return valid, llm_cost

    def _score_chunk_safe(
        self,
        chunk_index: int,
        rendered_prompt: str,
    ) -> tuple[int, list[dict], float, bool]:
        """Wrapper for thread pool use: returns (chunk_index, candidates, cost, failed)."""
        try:
            candidates, cost = self.score_chunk(rendered_prompt)
            return chunk_index, candidates, cost, False
        except Exception as exc:
            logger.error("Chunk %d failed after Groq failover chain: %s", chunk_index, exc)
            return chunk_index, [], 0.0, True

    def refine_clip_boundaries(
        self,
        candidate_clip: dict | ScoredClip,
        words: list[dict],
        context_window_s: float = 45.0,
    ) -> tuple[float, float, str | None, float]:
        orig_start = float(candidate_clip["start_time"])
        orig_end = float(candidate_clip["end_time"])
        
        window_start = max(0.0, orig_start - context_window_s)
        window_end = orig_end + (context_window_s / 3)
        
        relevant_words = [
            w for w in words 
            if float(w["end"]) >= window_start and float(w["start"]) <= window_end
        ]
        context_text = format_transcript_chunk(relevant_words)
        
        prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "clip_refinement.txt"
        if not prompt_path.exists():
            return orig_start, orig_end, None, 0.0
            
        template = PromptTemplate(prompt_path.read_text(encoding="utf-8"))
        rendered = template.substitute(
            clip_json=json.dumps({
                "start_time": orig_start,
                "end_time": orig_end,
                "reason": candidate_clip.get("reason", "")
            }),
            transcript_context=context_text,
            prompt_version=settings.clip_prompt_version,
        )
        
        try:
            from services.openai_client import create_chat_completion

            completion = create_chat_completion(
                client=self.client,
                preferred_model=settings.clip_detector_model,
                temperature=0.2,
                messages=[{"role": "user", "content": rendered}],
            )
            response = completion.response
            raw_content = response.choices[0].message.content or "{}"
            json_match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            refined_data = json.loads(json_match.group(0)) if json_match else json.loads(raw_content)
                
            new_start = float(refined_data.get("start_time", orig_start))
            new_end = float(refined_data.get("end_time", orig_end))
            reason = refined_data.get("refinement_reason", "Refined to capture story arc.")
            
            if not (window_start <= new_start < new_end <= window_end + 1.0):
                return orig_start, orig_end, None, 0.0
                
            if not (settings.min_clip_length_seconds <= (new_end - new_start) <= settings.max_clip_length_seconds):
                return orig_start, orig_end, None, 0.0

            usage = getattr(response, "usage", None)
            llm_cost = estimate_llm_cost_from_tokens(
                completion.model,
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
            )
            return new_start, new_end, reason, llm_cost
        except Exception:
            return orig_start, orig_end, None, 0.0

    def _finalize_heuristic_clips(
        self, 
        heuristic_candidates: list[dict], 
        effective_weights: dict[str, float] | None = None,
        user_id: str | None = None
    ) -> list[ScoredClip]:
        """Utility to convert raw heuristic candidates into ScoredClip objects."""
        if not effective_weights and user_id:
            from services.content_dna import get_personalized_weights
            effective_weights = get_personalized_weights(user_id)
        effective_weights = normalize_score_weights(effective_weights)

        all_candidates = []
        for candidate in heuristic_candidates:
            coerced_scores = {k: float(candidate[k]) for k in SCORE_WEIGHTS}
            all_candidates.append({
                **candidate,
                "duration": round(float(candidate["end_time"]) - float(candidate["start_time"]), 2),
                "final_score": calculate_final_score(coerced_scores, weights=effective_weights),
                "score_source": candidate.get("source", "heuristic"),
                "score_confidence": float(candidate.get("score_confidence", 0.38)),
            })

        deduped = dedupe_candidates(all_candidates)
        selected = select_top_clips(deduped, limit=10) # limit is handled by caller or just use high enough

        results: list[ScoredClip] = []
        for index, candidate in enumerate(selected, start=1):
            r_start = float(candidate["start_time"])
            r_end = float(candidate["end_time"])
            results.append(
                ScoredClip(
                    clip_index=index,
                    start_time=r_start,
                    end_time=r_end,
                    duration=round(r_end - r_start, 2),
                    clip_url=None,
                    hook_score=float(candidate["hook_score"]),
                    emotion_score=float(candidate["emotion_score"]),
                    clarity_score=float(candidate["clarity_score"]),
                    story_score=float(candidate["story_score"]),
                    virality_score=float(candidate["virality_score"]),
                    final_score=float(candidate["final_score"]),
                    reason=str(candidate["reason"]),
                    hook_headlines=list(candidate.get("hook_headlines", [])),
                    layout_suggestion=candidate.get("layout_suggestion", "vertical"),
                    refinement_reason="Heuristic fallback due to degraded service mode.",
                    score_source="heuristic",
                    score_confidence=0.38,
                )
            )
        return results

    def detect_clips(
        self,
        transcript_json: dict,
        prompt_version: str = "v4",
        custom_score_weights: dict[str, float] | None = None,
        custom_prompt_instruction: str | None = None,
        limit: int = 5,
        user_id: str | None = None,
    ) -> tuple[list[ScoredClip], float]:
        prompt_template, prompt_path = self.load_prompt(prompt_version)
        words = flatten_words(transcript_json)

        # Gap 363: Check health before starting expensive AI work
        mode = check_ai_health()
        if mode == ServiceMode.DEGRADED:
            logger.warning("Running in DEGRADED mode — skipping LLM and using heuristic fallback directly.")
            heuristic_candidates = build_heuristic_candidates(words, limit=limit)
            results = self._finalize_heuristic_clips(heuristic_candidates, effective_weights=None, user_id=user_id)
            return results, 0.0

        chunks = chunk_transcript(words)

        effective_weights = custom_score_weights
        if not effective_weights and user_id:
            effective_weights = get_personalized_weights(user_id)
        effective_weights = normalize_score_weights(effective_weights)

        if not chunks:
            return [], 0.0

        rendered_prompts: list[tuple[int, str]] = []
        for i, chunk_words in enumerate(chunks):
            prompt_text = _render_prompt(
                prompt_template,
                format_transcript_chunk(chunk_words),
                prompt_path,
            )
            if custom_prompt_instruction:
                prompt_text += f"\n\nAdditional instruction: {custom_prompt_instruction}"
            rendered_prompts.append((i, prompt_text))

        workers = min(MAX_SCORE_WORKERS, len(rendered_prompts))
        chunk_results: dict[int, tuple[list[dict], float, bool]] = {}

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self._score_chunk_safe, i, p): i for i, p in rendered_prompts}
            for future in as_completed(futures):
                try:
                    idx, candidates, cost, failed = future.result()
                    chunk_results[idx] = (candidates, cost, failed)
                except Exception as e:
                    # Gap 363: Detect outage and trip circuit breaker
                    if _is_provider_outage(e):
                        enter_degraded_mode(reason=str(e))
                        logger.error(f"AI Provider outage detected during scoring: {e}. Tripping circuit breaker.")
                    raise

        all_candidates: list[dict] = []
        total_cost = 0.0

        for i in sorted(chunk_results):
            candidates, chunk_cost, _ = chunk_results[i]
            total_cost += chunk_cost
            for candidate in candidates:
                start = float(candidate["start_time"])
                end = float(candidate["end_time"])
                duration = end - start
                if not (settings.min_clip_length_seconds <= duration <= settings.max_clip_length_seconds):
                    continue
                coerced_scores = {k: float(candidate[k]) for k in SCORE_WEIGHTS}
                scored = {
                    **candidate,
                    "duration": round(duration, 2),
                    "final_score": calculate_final_score(coerced_scores, weights=effective_weights),
                    "score_source": candidate.get("source", "llm"),
                    "score_confidence": float(candidate.get("score_confidence", 1.0)),
                }
                if scored["final_score"] >= SCORE_THRESHOLD:
                    all_candidates.append(scored)

        if not all_candidates:
            logger.info("LLM detection produced no valid candidates; using heuristic fallback candidates.")
            for candidate in build_heuristic_candidates(words, limit=limit):
                coerced_scores = {k: float(candidate[k]) for k in SCORE_WEIGHTS}
                all_candidates.append(
                    {
                        **candidate,
                        "duration": round(float(candidate["end_time"]) - float(candidate["start_time"]), 2),
                        "final_score": calculate_final_score(coerced_scores, weights=effective_weights),
                        "score_source": candidate.get("source", "heuristic"),
                        "score_confidence": float(candidate.get("score_confidence", 0.38)),
                    }
                )

        deduped = dedupe_candidates(all_candidates)
        selected = select_top_clips(deduped, limit=limit)

        results: list[ScoredClip] = []
        for index, candidate in enumerate(selected, start=1):
            if candidate.get("source") == "heuristic":
                r_start = float(candidate["start_time"])
                r_end = float(candidate["end_time"])
                r_reason = "Heuristic fallback boundaries used because LLM detection did not return valid candidates."
                r_cost = 0.0
            else:
                r_start, r_end, r_reason, r_cost = self.refine_clip_boundaries(candidate, words)
            total_cost += r_cost
            results.append(
                ScoredClip(
                    clip_index=index,
                    start_time=r_start,
                    end_time=r_end,
                    duration=round(r_end - r_start, 2),
                    clip_url=None,
                    hook_score=float(candidate["hook_score"]),
                    emotion_score=float(candidate["emotion_score"]),
                    clarity_score=float(candidate["clarity_score"]),
                    story_score=float(candidate["story_score"]),
                    virality_score=float(candidate["virality_score"]),
                    final_score=float(candidate["final_score"]),
                    reason=str(candidate["reason"]),
                    hook_headlines=list(candidate.get("hook_headlines", [])),
                    layout_suggestion=candidate.get("layout_suggestion", "vertical"),
                    refinement_reason=r_reason,
                    score_source=str(candidate.get("score_source", candidate.get("source", "llm"))),
                    score_confidence=float(candidate.get("score_confidence", 1.0 if candidate.get("source") != "heuristic" else 0.38)),
                )
            )
        return results, round(total_cost, 6)


def get_clip_detector_service() -> ClipDetectorService:
    return ClipDetectorService()
