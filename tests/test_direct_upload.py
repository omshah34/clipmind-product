"""Tests for direct browser-to-storage upload flow."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from api.models.job import DirectUploadCompleteRequest, DirectUploadInitRequest
from api.routes.upload import complete_direct_upload, init_direct_upload


class DirectUploadRouteTests(unittest.TestCase):
    def test_init_direct_upload_returns_signed_url_and_job(self) -> None:
        request = DirectUploadInitRequest(
            filename="video.mp4",
            size_bytes=1024,
            duration_seconds=180.0,
        )

        fake_job = MagicMock(
            id=uuid4(),
            created_at=datetime.now(timezone.utc),
        )

        with (
            patch("api.routes.upload.storage_service.is_cloud_storage_enabled", return_value=True),
            patch("api.routes.upload.storage_service.create_signed_upload_url", return_value=("uploads/test.mp4", "https://storage.example/upload", "token")),
            patch("api.routes.upload.storage_service.build_public_url", return_value="https://storage.example/public/test.mp4"),
            patch("api.routes.upload.create_job", return_value=fake_job),
        ):
            response = init_direct_upload(request)

        self.assertEqual(response.job_id, fake_job.id)
        self.assertEqual(response.status, "uploading")
        self.assertEqual(response.upload_url, "https://storage.example/upload")

    def test_complete_direct_upload_queues_processing(self) -> None:
        job_id = uuid4()
        fake_job = MagicMock(
            id=job_id,
            created_at=datetime.now(timezone.utc),
        )

        with (
            patch("api.routes.upload.get_job", return_value=fake_job),
            patch("api.routes.upload.update_job") as mock_update_job,
            patch("api.routes.upload.dispatch_task") as mock_dispatch,
        ):
            response = complete_direct_upload(DirectUploadCompleteRequest(job_id=job_id))

        self.assertEqual(response.job_id, job_id)
        self.assertEqual(response.status, "uploaded")
        mock_update_job.assert_called_once_with(job_id, status="uploaded")
        mock_dispatch.assert_called_once()


if __name__ == "__main__":
    unittest.main()
