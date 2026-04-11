import unittest
from pathlib import Path

from services.video_processor import build_subtitle_filter


class VideoProcessorTests(unittest.TestCase):
    def test_build_subtitle_filter_contains_required_steps(self) -> None:
        filter_expression = build_subtitle_filter(Path("captions.srt"))
        self.assertIn("crop=ih*9/16:ih:(iw-ih*9/16)/2:0", filter_expression)
        self.assertIn("scale=1080:1920", filter_expression)
        self.assertIn("subtitles=", filter_expression)
        self.assertIn("FontSize=22", filter_expression)


if __name__ == "__main__":
    unittest.main()
