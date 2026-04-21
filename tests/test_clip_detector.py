"""File: tests/test_clip_detector.py
Purpose: Verify clip detection, LLM scoring, segment selection, and
         score thresholding logic matches codex_identity.md rules.
"""

import unittest

from services.clip_detector import (
    calculate_final_score,
    chunk_transcript,
    select_top_clips,
)


class ClipDetectorTests(unittest.TestCase):
    def test_calculates_weighted_score(self) -> None:
        score = calculate_final_score(
            {
                "hook_score": 8,
                "emotion_score": 7,
                "clarity_score": 9,
                "story_score": 6,
                "virality_score": 7,
            }
        )
        self.assertAlmostEqual(score, 7.55, places=2)

    def test_select_top_clips_skips_overlap(self) -> None:
        selected = select_top_clips(
            [
                {"start_time": 0, "end_time": 40, "final_score": 8.2, "hook_score": 9},
                {"start_time": 20, "end_time": 55, "final_score": 8.8, "hook_score": 8},
                {"start_time": 60, "end_time": 95, "final_score": 7.1, "hook_score": 7},
            ]
        )

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["start_time"], 20)
        self.assertEqual(selected[1]["start_time"], 60)

    def test_chunks_transcript(self) -> None:
        words = [
            {"word": "hello", "start": 0.0, "end": 0.5},
            {"word": "world", "start": 10.0, "end": 10.5},
            {"word": "again", "start": 301.0, "end": 301.5},
        ]
        chunks = chunk_transcript(words)
        self.assertGreaterEqual(len(chunks), 2)


if __name__ == "__main__":
    unittest.main()
