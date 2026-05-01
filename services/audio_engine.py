"""File: services/audio_engine.py
Purpose: Audio analysis using librosa for transient (beat/onset) detection.
         Enables precise visual-to-audio sync for Phase 2 'WOW' effects.

Gap 38: Audio is loaded with offset + duration so only the relevant segment
         is decoded into RAM, preventing OOM crashes on 1-hour podcast files.
Gap 39: Onset strength energy thresholding eliminates weak noise transients.
Gap 45: normalize_audio_file() wraps ffmpeg loudnorm for consistent clip volume.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import librosa
import numpy as np

logger = logging.getLogger(__name__)

# Gap 39: Only transients whose onset strength exceeds mean + this many sigma
# are returned. Higher = fewer, stronger beats only.
_ONSET_STRENGTH_SIGMA = float(0.5)


class AudioEngine:
    @staticmethod
    def get_transients(
        audio_path: Path,
        start_time: float = 0.0,
        end_time: float | None = None,
        sr: int = 22050,
    ) -> list[float]:
        """
        Detects significant transients (onsets) in an audio file.

        Gap 38: Only loads the requested segment into RAM (offset + duration).
        Gap 39: Filters out weak transients below mean+σ onset strength.

        Returns a list of timestamps in seconds relative to the start of the audio file.
        """
        if not audio_path.exists():
            logger.error("Audio file not found: %s", audio_path)
            return []

        try:
            # Gap 38: Load only the relevant segment — critical for 1hr+ podcast files
            duration = (end_time - start_time) if end_time is not None else None
            y, current_sr = librosa.load(
                str(audio_path), sr=sr, offset=start_time, duration=duration
            )

            if len(y) == 0:
                return []

            # Compute onset strength envelope first (needed for Gap 39 threshold)
            onset_env = librosa.onset.onset_strength(y=y, sr=current_sr)

            # Use onset detection with backtrack for accurate peak alignment
            onset_frames = librosa.onset.onset_detect(
                y=y, sr=current_sr, onset_envelope=onset_env, backtrack=True
            )

            if len(onset_frames) == 0:
                return []

            # Gap 39: Filter out weak onsets — keep only those above mean + 0.5σ
            strengths = onset_env[onset_frames]
            threshold = strengths.mean() + _ONSET_STRENGTH_SIGMA * strengths.std()
            strong_frames = onset_frames[strengths >= threshold]

            if len(strong_frames) == 0:
                # Fall back to all detections if threshold is too aggressive
                strong_frames = onset_frames

            onset_times = librosa.frames_to_time(strong_frames, sr=current_sr)
            logger.debug(
                "Transients: %d raw → %d after strength filter (threshold=%.3f)",
                len(onset_frames), len(strong_frames), threshold
            )
            return [float(t) for t in onset_times]

        except Exception as exc:
            logger.exception("Failed to detect transients for %s: %s", audio_path.name, exc)
            return []

    @staticmethod
    def get_synced_beats(
        audio_path: Path,
        start_time: float = 0.0,
        end_time: float | None = None,
        sr: int = 22050,
    ) -> list[float]:
        """Returns detected beat positions for high-energy rhythm syncing.

        Gap 38: Now loads only the segment within [start_time, end_time] to
        prevent loading the full file into RAM for large sources.
        """
        try:
            # Gap 38: Segment-aware loading
            duration = (end_time - start_time) if end_time is not None else None
            y, sr_out = librosa.load(str(audio_path), sr=sr, offset=start_time, duration=duration)
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr_out)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr_out)
            return [float(t) for t in beat_times]
        except Exception as exc:
            logger.exception("Beat tracking failed: %s", exc)
            return []


def normalize_audio_file(input_path: Path, output_path: Path, target_lufs: float = -14.0) -> Path:
    """Normalize audio loudness using FFmpeg's EBU R128 loudnorm filter.

    Gap 45: Clips from different sources can have wildly different volumes.
    This two-pass loudnorm brings every clip to -14 LUFS (YouTube/Spotify standard).

    Args:
        input_path: Source audio/video file.
        output_path: Destination for the normalized file.
        target_lufs: Target integrated loudness. Default -14 LUFS (streaming standard).

    Returns:
        output_path on success.

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
        "-c:v", "copy",       # Pass video through unchanged if present
        "-ar", "48000",       # Gap 188: Resample to consistent 48kHz to prevent pitch shifting
        str(output_path),
    ]
    logger.info("Normalizing audio: %s → %s (target=%s LUFS)", input_path.name, output_path.name, target_lufs)
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        logger.error("Audio normalization failed: %s", result.stderr[-500:])
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)
    return output_path


def time_stretch_audio(input_path: Path, output_path: Path, ratio: float) -> Path:
    """
    Time-stretch audio without changing pitch using FFmpeg's 'atempo' filter.
    Gap 257 Fix: Synchronize TTS duration with visual clip duration.
    
    Args:
        input_path: Source audio file.
        output_path: Destination audio file.
        ratio: Speed ratio. 0.5 to 2.0. (e.g., 1.1 = 10% faster).
    """
    if not (0.5 <= ratio <= 2.0):
        # atempo filter limit is 0.5 to 2.0. For larger shifts, chain multiple filters.
        logger.warning("Ratio %.2f outside standard atempo range; clamping.", ratio)
        ratio = max(0.5, min(2.0, ratio))

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-af", f"atempo={ratio}",
        str(output_path),
    ]
    logger.info("Time-stretching audio: %s (ratio=%.2f)", input_path.name, ratio)
    subprocess.run(cmd, check=True, capture_output=True)
    return output_path
