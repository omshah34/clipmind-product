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
import json
import logging
import re
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

        opening_words = " ".join(str(w.get("word", "")).strip() for w in words[start_idx : start_idx + 10]).strip()
        candidates.append(
            {
                "source": "heuristic",
                "start_time": round(start_time, 2),
                "end_time": round(end_time, 2),
                "hook_score": 7.0,
                "emotion_score": 6.5,
                "clarity_score": 7.0,
                "story_score": 6.5,
                "virality_score": 7.0,
                "reason": f"Fallback candidate beginning with '{opening_words}' selected after LLM clip detection did not return usable candidates.",
                "hook_headlines": [
                    "You can automate this now",
                    "Stop doing this manually",
                    "Your workflow can run itself",
                ],
                "layout_suggestion": "vertical",
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
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is required for clip detection")
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
        response = self.client.chat.completions.create(
            model=model,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content or "[]", response

    @retry(
        reraise=True,
        stop=stop_after_attempt(settings.clip_detector_retry_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError, RateLimitError)),
    )
    def score_chunk(self, rendered_prompt: str, model_override: str | None = None) -> tuple[list[dict], float]:
        """Call the LLM, parse candidates, and return (candidates, cost)."""
        model = model_override or settings.clip_detector_model
        raw_content, response = self._call_llm(rendered_prompt, model)

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
            model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )

        logger.debug("Chunk scored (%s): %d valid, cost=$%.6f", model, len(valid), llm_cost)
        return valid, llm_cost

    def _score_chunk_safe(
        self,
        chunk_index: int,
        rendered_prompt: str,
    ) -> tuple[int, list[dict], float, bool]:
        """Wrapper for thread pool use: returns (chunk_index, candidates, cost, failed).
        Gap 40: Fallback to secondary model on persistent failure.
        """
        try:
            candidates, cost = self.score_chunk(rendered_prompt)
            return chunk_index, candidates, cost, False
        except Exception as primary_exc:
            fallback_model = settings.clip_detector_fallback_model.strip()
            if not fallback_model or fallback_model == settings.clip_detector_model:
                logger.info(
                    "Chunk %d primary model (%s) failed: %s. No fallback model configured.",
                    chunk_index,
                    settings.clip_detector_model,
                    primary_exc,
                )
                return chunk_index, [], 0.0, True

            logger.info(
                "Chunk %d primary model (%s) failed: %s. Trying fallback (%s)...",
                chunk_index, settings.clip_detector_model, primary_exc, 
                fallback_model
            )
            try:
                candidates, cost = self.score_chunk(
                    rendered_prompt, 
                    model_override=fallback_model
                )
                return chunk_index, candidates, cost, False
            except Exception as fallback_exc:
                logger.error("Chunk %d fallback model also failed: %s", chunk_index, fallback_exc)
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
            response = self.client.chat.completions.create(
                model=settings.clip_detector_model,
                temperature=0.2,
                messages=[{"role": "user", "content": rendered}],
            )
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
                settings.clip_detector_model,
                getattr(usage, "prompt_tokens", None),
                getattr(usage, "completion_tokens", None),
            )
            return new_start, new_end, reason, llm_cost
        except Exception:
            return orig_start, orig_end, None, 0.0

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
                idx, candidates, cost, failed = future.result()
                chunk_results[idx] = (candidates, cost, failed)

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
                    refinement_reason=r_reason
                )
            )
        return results, round(total_cost, 6)


def get_clip_detector_service() -> ClipDetectorService:
    return ClipDetectorService()
