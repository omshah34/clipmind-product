"""File: services/diarization_utils.py
Purpose: Utilities for cleaning and merging diarization outputs.
         Fixes fragmented speaker boundaries by merging consecutive segments.
"""

import logging

logger = logging.getLogger(__name__)

def merge_speaker_segments(
    segments: list[dict],
    gap_threshold_s: float = 1.5,
) -> list[dict]:
    """
    Merge consecutive segments from the same speaker if the gap between them 
    is less than gap_threshold_s.
    
    Args:
        segments: List of dicts with 'speaker', 'start', 'end' keys.
        gap_threshold_s: Maximum gap to merge (default 1.5s).
    """
    if not segments:
        return []

    # Sort by start time just in case
    sorted_segments = sorted(segments, key=lambda s: s["start"])
    
    merged = []
    current = sorted_segments[0].copy()

    for next_seg in sorted_segments[1:]:
        # Same speaker AND short gap
        if (next_seg["speaker"] == current["speaker"] and 
            (next_seg["start"] - current["end"]) <= gap_threshold_s):
            
            # Merge: extend end time
            current["end"] = max(current["end"], next_seg["end"])
            # If segments have 'text' or 'words', they should also be merged/extended
            if "text" in current and "text" in next_seg:
                current["text"] += " " + next_seg["text"]
            if "words" in current and "words" in next_seg:
                current["words"].extend(next_seg["words"])
        else:
            merged.append(current)
            current = next_seg.copy()
    
    merged.append(current)
    
    logger.info("Merged %d segments into %d segments (threshold=%.1fs)", 
                len(segments), len(merged), gap_threshold_s)
    return merged
