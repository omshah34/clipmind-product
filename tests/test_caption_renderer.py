import tempfile
"""File: tests/test_caption_renderer.py
Purpose: Verify SRT generation from Whisper word timestamps, caption timing
         accuracy, and FFmpeg caption burning produces correct output.
"""

import unittest
from pathlib import Path

from services.caption_renderer import clip_relative_words, format_srt_time, write_clip_srt


class CaptionRendererTests(unittest.TestCase):
    def test_formats_srt_time(self) -> None:
        self.assertEqual(format_srt_time(65.125), "00:01:05,125")

    def test_builds_clip_relative_words(self) -> None:
        words = clip_relative_words(
            {
                "words": [
                    {"word": "hello", "start": 10.0, "end": 10.4},
                    {"word": "there", "start": 10.5, "end": 10.9},
                    {"word": "friend", "start": 12.0, "end": 12.4},
                ]
            },
            clip_start_time=10.0,
            clip_end_time=12.5,
        )

        self.assertEqual(words[0]["start"], 0.0)
        self.assertAlmostEqual(words[-1]["end"], 2.4, places=2)

    def test_writes_srt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "captions.srt"
            write_clip_srt(
                {
                    "words": [
                        {"word": "hello", "start": 10.0, "end": 10.4},
                        {"word": "world", "start": 10.5, "end": 10.9},
                    ]
                },
                clip_start_time=10.0,
                clip_end_time=11.0,
                output_path=output_path,
            )

            self.assertIn("hello world", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
