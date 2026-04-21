"""File: services/transcription.py
Purpose: Whisper API wrapper with multi-model fallback and automatic audio chunking.
         
         Uses Groq Whisper models in priority order. If one model hits a rate
         limit, it automatically falls back to the next model — ensuring maximum
         uptime without manual intervention.
         
         Audio files larger than 24MB are automatically split into time-based
         chunks using FFmpeg, transcribed individually, and stitched back together
         with correct time offsets.

Model fallback chain:
  1. whisper-large-v3          — best quality, highest accuracy
  2. whisper-large-v3-turbo    — fast, near-identical accuracy
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from services.caption_renderer import flatten_words
from services.cost_tracker import estimate_whisper_cost
from services.openai_client import make_openai_client

logger = logging.getLogger(__name__)

# Ordered by quality — best first, fastest last
WHISPER_MODELS = [
    "whisper-large-v3",
    "whisper-large-v3-turbo",
]

# Groq limit is 25MB; use 24MB as safe threshold
_MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024

# Chunk duration in seconds (from config, default 5 min)
_CHUNK_DURATION_SECONDS = settings.transcript_chunk_minutes * 60
_CHUNK_OVERLAP_SECONDS = settings.transcript_chunk_overlap_seconds


def _is_valid_transcript(transcript: dict | None) -> bool:
    """Validate that a transcript has the required structure.
    
    Accepts transcripts even without segments - Groq API doesn't guarantee them.
    """
    return isinstance(transcript, dict) and "text" in transcript


def _get_audio_duration(audio_path: Path) -> float:
    """Get audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return float(result.stdout.strip())


def _split_audio(audio_path: Path, chunk_dir: Path) -> list[tuple[Path, float]]:
    """Split audio into chunks that fit under the Groq size limit.
    
    Returns list of (chunk_path, start_offset_seconds) tuples.
    """
    total_duration = _get_audio_duration(audio_path)
    file_size = audio_path.stat().st_size

    # If file is small enough, return as-is
    if file_size <= _MAX_FILE_SIZE_BYTES:
        logger.info("Audio file %.1fMB — no chunking needed.", file_size / (1024 * 1024))
        return [(audio_path, 0.0)]

    logger.info(
        "Audio file %.1fMB exceeds %.0fMB limit. Splitting into ~%d-min chunks.",
        file_size / (1024 * 1024),
        _MAX_FILE_SIZE_BYTES / (1024 * 1024),
        _CHUNK_DURATION_SECONDS // 60,
    )

    chunks: list[tuple[Path, float]] = []
    start = 0.0
    chunk_index = 0

    while start < total_duration:
        chunk_path = chunk_dir / f"chunk_{chunk_index:03d}.mp3"
        duration = min(_CHUNK_DURATION_SECONDS, total_duration - start)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", str(audio_path),
            "-t", str(duration),
            "-acodec", "mp3",
            "-q:a", "2",
            str(chunk_path),
        ]
        subprocess.run(cmd, capture_output=True, check=True)

        chunks.append((chunk_path, start))
        logger.debug(
            "Chunk %d: offset=%.1fs, duration=%.1fs, path=%s",
            chunk_index, start, duration, chunk_path.name,
        )

        chunk_index += 1
        # Advance by chunk duration minus overlap for continuity
        start += _CHUNK_DURATION_SECONDS - _CHUNK_OVERLAP_SECONDS

    logger.info("Split into %d chunks.", len(chunks))
    return chunks


def _merge_transcripts(
    chunk_results: list[tuple[dict, float]],
) -> dict:
    """Merge chunk transcripts into a single transcript with corrected time offsets.
    
    Args:
        chunk_results: List of (transcript_json, start_offset_seconds) tuples.
    """
    merged_text_parts: list[str] = []
    merged_words: list[dict] = []
    merged_segments: list[dict] = []
    total_duration = 0.0

    for transcript, offset in chunk_results:
        # SAFETY FIX: Skip None transcripts
        if transcript is None:
            logger.error("Found None transcript — skipping chunk")
            continue
        
        # Merge text
        text = transcript.get("text", "")
        if text:
            merged_text_parts.append(text.strip())

        # Merge words with time offset
        words = flatten_words(transcript)
        for word in words:
            adjusted_word = {
                **word,
                "start": float(word["start"]) + offset,
                "end": float(word["end"]) + offset,
            }
            merged_words.append(adjusted_word)

        # Merge segments with time offset
        # Handle case where segments is None or missing
        segments = transcript.get("segments") or []
        for seg in segments:
            adjusted_seg = {
                **seg,
                "start": float(seg.get("start", 0)) + offset,
                "end": float(seg.get("end", 0)) + offset,
            }
            # Adjust words within segment too
            if "words" in adjusted_seg:
                adjusted_seg["words"] = [
                    {**w, "start": float(w["start"]) + offset, "end": float(w["end"]) + offset}
                    for w in adjusted_seg["words"]
                ]
            merged_segments.append(adjusted_seg)

        # Track total duration
        if words:
            total_duration = max(total_duration, float(words[-1]["end"]) + offset)

    # De-duplicate overlapping words (from chunk overlap)
    merged_words = _deduplicate_words(merged_words)

    return {
        "text": " ".join(merged_text_parts),
        "words": merged_words,
        "segments": merged_segments,
        "language": chunk_results[0][0].get("language", "en") if chunk_results else "en",
        "duration": total_duration,
    }


def _deduplicate_words(words: list[dict]) -> list[dict]:
    """Remove duplicate words from overlapping chunk boundaries.
    
    Words are considered duplicates if they have very similar timestamps
    and the same text.
    """
    if not words:
        return words

    # Sort by start time
    words.sort(key=lambda w: float(w["start"]))

    deduped: list[dict] = [words[0]]
    for word in words[1:]:
        prev = deduped[-1]
        # If start times are within 0.5s and same word text, skip (duplicate)
        time_diff = abs(float(word["start"]) - float(prev["start"]))
        same_text = word.get("word", "").strip().lower() == prev.get("word", "").strip().lower()
        if time_diff < 0.5 and same_text:
            continue
        deduped.append(word)

    return deduped


class TranscriptionService:
    def __init__(self) -> None:
        if not settings.whisper_api_key and not settings.openai_api_key:
            raise RuntimeError("WHISPER_API_KEY or OPENAI_API_KEY is required for transcription")
        self.client = make_openai_client(for_whisper=True)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type((APIConnectionError, APITimeoutError)),
    )
    def _call_whisper(self, audio_path: Path, model: str, language: str | None = None) -> dict:
        """Call a single Whisper model. Retries on connection/timeout errors only."""
        with audio_path.open("rb") as audio_file:
            # Prepare arguments
            params = {
                "model": model,
                "file": audio_file,
                "response_format": "verbose_json",
                "timestamp_granularities": ["word", "segment"],
            }
            if language:
                params["language"] = language
                
            response = self.client.audio.transcriptions.create(**params)
        return response.model_dump() if hasattr(response, "model_dump") else dict(response)

    def _transcribe_single(self, audio_path: Path, language: str | None = None) -> dict:
        """Try each Whisper model in order for a single audio file."""
        last_error: Exception | None = None

        for i, model in enumerate(WHISPER_MODELS):
            try:
                logger.info("Transcribing with model '%s' (%d/%d) [lang=%s]", model, i + 1, len(WHISPER_MODELS), language)
                transcript = self._call_whisper(audio_path, model, language)

                # CRITICAL FIX: Validate response has minimum required fields
                if not transcript or not isinstance(transcript, dict):
                    raise ValueError(f"Invalid transcript from model {model}: not a valid dict")

                if "text" not in transcript:
                    raise ValueError(f"Transcript missing 'text' field from model {model}")

                # DEBUG: Show what fields we got
                logger.info("Transcript keys: %s", list(transcript.keys()))

                # AUTO-GENERATE segments if missing or None (Groq API doesn't guarantee them)
                if not transcript.get("segments"):
                    logger.warning("No segments or segments=None from model %s — auto-creating empty list", model)
                    transcript["segments"] = []

                logger.info("Transcription succeeded with model '%s'", model)
                return transcript

            except RateLimitError as exc:
                last_error = exc
                remaining = len(WHISPER_MODELS) - i - 1
                if remaining > 0:
                    logger.warning(
                        "Model '%s' rate-limited. Falling back to next model (%d remaining).",
                        model, remaining,
                    )
                else:
                    logger.error("All %d Whisper models rate-limited.", len(WHISPER_MODELS))

            except Exception as exc:
                logger.error("Model '%s' failed: %s", model, exc)
                last_error = exc
                continue

        raise last_error  # type: ignore[misc]

    def transcribe_audio(self, audio_path: Path, language: str | None = None) -> tuple[dict, float]:
        """Transcribe audio with automatic chunking for large files."""
        # Create temp dir for chunks within the audio's parent dir
        chunk_dir = Path(tempfile.mkdtemp(
            prefix="whisper_chunks_",
            dir=audio_path.parent,
        ))

        try:
            chunks = _split_audio(audio_path, chunk_dir)

            if len(chunks) == 1:
                # Single file — no chunking needed
                transcript_json = self._transcribe_single(chunks[0][0], language)
                transcript_json["words"] = flatten_words(transcript_json)
                words = transcript_json["words"]
                duration = float(words[-1]["end"]) if words else 0.0
                return transcript_json, estimate_whisper_cost(duration)

            # Multi-chunk: transcribe each and merge
            chunk_results: list[tuple[dict, float]] = []
            for idx, (chunk_path, offset) in enumerate(chunks):
                logger.info(
                    "Transcribing chunk %d/%d (offset=%.1fs, lang=%s)...",
                    idx + 1, len(chunks), offset, language
                )
                transcript = self._transcribe_single(chunk_path, language)
                
                # FIX 3: Filter bad chunks — skip if transcription failed
                if transcript is None or not _is_valid_transcript(transcript):
                    logger.error("Chunk %d transcription failed — skipping", idx + 1)
                    continue

                chunk_results.append((transcript, offset))

            # FIX 4: Fail fast if all chunks failed
            if not chunk_results:
                raise RuntimeError("All transcription chunks failed")

            merged = _merge_transcripts(chunk_results)
            words = merged["words"]
            duration = float(words[-1]["end"]) if words else 0.0

            logger.info(
                "Merged %d chunks → %d words, %.1fs total duration.",
                len(chunks), len(words), duration,
            )
            return merged, estimate_whisper_cost(duration)

        finally:
            # Clean up chunk files
            import shutil
            try:
                shutil.rmtree(chunk_dir)
            except Exception:
                pass


def get_transcription_service() -> TranscriptionService:
    return TranscriptionService()
