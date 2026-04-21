"""File: tests/test_upload.py
Purpose: Verify upload file validation, size constraints, duration checks,
         and format restrictions match codex_identity.md specification.
"""

import unittest

from api.routes.upload import UploadValidationError, validate_upload_constraints


class UploadValidationTests(unittest.TestCase):
    def test_accepts_valid_upload(self) -> None:
        validate_upload_constraints(
            filename="episode.mp4",
            size_bytes=100 * 1024 * 1024,
            duration_seconds=15 * 60,
        )

    def test_rejects_invalid_extension(self) -> None:
        with self.assertRaises(UploadValidationError) as context:
            validate_upload_constraints(
                filename="episode.avi",
                size_bytes=100,
                duration_seconds=15 * 60,
            )

        self.assertEqual(context.exception.error, "invalid_format")

    def test_rejects_short_duration(self) -> None:
        with self.assertRaises(UploadValidationError) as context:
            validate_upload_constraints(
                filename="episode.mov",
                size_bytes=100,
                duration_seconds=30,
            )

        self.assertEqual(context.exception.error, "duration_too_short")


if __name__ == "__main__":
    unittest.main()
