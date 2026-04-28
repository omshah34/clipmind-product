"""File: tests/test_video_processor.py
Purpose: Test FFmpeg audio extraction, clip cutting, vertical cropping,
         and export logic matches exact commands in codex_identity.md.
"""

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.video_processor import (
    FFmpegError,
    build_subtitle_filter,
    get_video_encoder,
    _run_command_with_encoder_fallback,
    _video_encoder_args,
)


class VideoProcessorTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_video_encoder.cache_clear()

    def test_build_subtitle_filter_contains_required_steps(self) -> None:
        filter_expression = build_subtitle_filter(Path("captions.srt"))
        self.assertIn("crop=ih*9/16:ih:(iw-ih*9/16)/2:0", filter_expression)
        self.assertIn("scale=1080:1920", filter_expression)
        self.assertIn("subtitles=", filter_expression)
        self.assertIn("FontSize=22", filter_expression)

    def test_get_video_encoder_falls_back_when_nvenc_is_unusable(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" V..... h264_nvenc ", stderr="")
        nvenc_probe = MagicMock(returncode=1, stdout="", stderr="Driver does not support the required nvenc API version")

        with patch.dict("os.environ", {"CLIPMIND_VIDEO_ENCODER": "auto"}):
            with patch("services.video_processor.subprocess.run", side_effect=[encoders, nvenc_probe]) as run_mock:
                encoder = get_video_encoder()

        self.assertEqual(encoder, "libx264")
        self.assertEqual(run_mock.call_count, 2)

    def test_get_video_encoder_defaults_to_libx264_without_probe(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with patch("services.video_processor.subprocess.run") as run_mock:
                encoder = get_video_encoder()

        self.assertEqual(encoder, "libx264")
        run_mock.assert_not_called()

    def test_get_video_encoder_uses_nvenc_when_probe_succeeds(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" V..... h264_nvenc ", stderr="")
        nvenc_probe = MagicMock(returncode=0, stdout="", stderr="")

        with patch.dict("os.environ", {"CLIPMIND_VIDEO_ENCODER": "auto"}):
            with patch("services.video_processor.subprocess.run", side_effect=[encoders, nvenc_probe]):
                encoder = get_video_encoder()

        self.assertEqual(encoder, "h264_nvenc")

    def test_get_video_encoder_uses_nvenc_when_requested_and_probe_succeeds(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" V..... h264_nvenc ", stderr="")
        nvenc_probe = MagicMock(returncode=0, stdout="", stderr="")

        with patch.dict("os.environ", {"CLIPMIND_VIDEO_ENCODER": "h264_nvenc"}):
            with patch("services.video_processor.subprocess.run", side_effect=[encoders, nvenc_probe]):
                encoder = get_video_encoder()

        self.assertEqual(encoder, "h264_nvenc")

    def test_nvenc_args_use_native_quality_option(self) -> None:
        args = _video_encoder_args("h264_nvenc", crf=23, preset="fast")

        self.assertIn("-cq", args)
        self.assertNotIn("-crf", args)
        self.assertEqual(args[args.index("-c:v") + 1], "h264_nvenc")

    def test_nvenc_runtime_failure_retries_with_libx264(self) -> None:
        command = [
            "ffmpeg",
            "-i",
            "in.mp4",
            "-c:v",
            "h264_nvenc",
            "-rc",
            "vbr",
            "-cq",
            "20",
            "-preset",
            "p4",
            "-pix_fmt",
            "yuv420p",
            "out.mp4",
        ]
        nvenc_error = FFmpegError(command, "Error while opening encoder", -22)
        completed = MagicMock(returncode=0)

        with patch("services.video_processor._run_command", side_effect=[nvenc_error, completed]) as run_mock:
            result = _run_command_with_encoder_fallback(command, crf=23, preset="fast")

        self.assertIs(result, completed)
        fallback_command = run_mock.call_args_list[1].args[0]
        self.assertIn("libx264", fallback_command)
        self.assertNotIn("h264_nvenc", fallback_command)
        self.assertIn("-crf", fallback_command)


if __name__ == "__main__":
    unittest.main()
