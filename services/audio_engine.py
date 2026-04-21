"""File: services/audio_engine.py
Purpose: Audio analysis using librosa for transient (beat/onset) detection.
         Enables precise visual-to-audio sync for Phase 2 'WOW' effects.
"""

from __future__ import annotations

import logging
from pathlib import Path
import librosa
import numpy as np

logger = logging.getLogger(__name__)

class AudioEngine:
    @staticmethod
    def get_transients(
        audio_path: Path, 
        start_time: float = 0.0, 
        end_time: float | None = None,
        sr: int = 22050
    ) -> list[float]:
        """
        Detects significant transients (onsets) in an audio file.
        Returns a list of timestamps in seconds relative to the start of the audio file.
        """
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return []

        try:
            # Load only the relevant segment if possible, or load full
            # Loading segment-wise is faster for large files
            duration = end_time - start_time if end_time else None
            y, current_sr = librosa.load(str(audio_path), sr=sr, offset=start_time, duration=duration)
            
            if len(y) == 0:
                return []

            # Use onset detection to find 'hits' or 'beats'
            # backtrack=True helps align the timestamp with the actual peak
            onset_frames = librosa.onset.onset_detect(y=y, sr=current_sr, backtrack=True)
            onset_times = librosa.frames_to_time(onset_frames, sr=current_sr)
            
            # Significant transients (filtering out minor noise)
            # librosa.onset.onset_detect is already fairly good, but we can refine
            # if necessary using onset_strength
            
            # Return as a list of floats
            return [float(t) for t in onset_times]

        except Exception as exc:
            logger.exception(f"Failed to detect transients for {audio_path.name}: {exc}")
            return []

    @staticmethod
    def get_synced_beats(audio_path: Path) -> list[float]:
        """Returns detected beat positions for high-energy rhythm syncing."""
        try:
            y, sr = librosa.load(str(audio_path))
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)
            return [float(t) for t in beat_times]
        except Exception as exc:
            logger.exception(f"Beat tracking failed: {exc}")
            return []
