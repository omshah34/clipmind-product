"""Tests for direct browser-to-storage upload flow."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

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
            patch("api.routes.upload.create_job", return_value=fake_job) as mock_create_job,
        ):
            response = init_direct_upload(request)

        self.assertEqual(response.job_id, str(fake_job.id))
        self.assertEqual(response.status, "uploading")
        self.assertEqual(response.upload_url, "https://storage.example/upload")
        persisted_url = mock_create_job.call_args.kwargs["source_video_url"]
        parsed = urlparse(persisted_url)
        self.assertEqual(parse_qs(parsed.query).get("cm_expected_size"), ["1024"])

    def test_complete_direct_upload_queues_processing(self) -> None:
        job_id = uuid4()
        payload = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        fake_job = MagicMock(
            id=job_id,
            created_at=datetime.now(timezone.utc),
            status="uploading",
            source_video_url="https://storage.example/public/uploads/test.mp4?cm_expected_size=24",
        )

        def fake_download(source_url: str, target_path) -> object:
            target_path.write_bytes(payload)
            return target_path

        with (
            patch("api.routes.upload.get_job", return_value=fake_job),
            patch("api.routes.upload.storage_service.extract_object_path", return_value="uploads/test.mp4"),
            patch("api.routes.upload.storage_service.object_exists", return_value=True),
            patch("api.routes.upload.storage_service.download_to_local", side_effect=fake_download),
            patch("api.routes.upload.update_job") as mock_update_job,
            patch("api.routes.upload.dispatch_task") as mock_dispatch,
        ):
            response = complete_direct_upload(DirectUploadCompleteRequest(job_id=str(job_id)))

        self.assertEqual(response.job_id, str(job_id))
        self.assertEqual(response.status, "uploaded")
        mock_update_job.assert_called_once_with(job_id, status="uploaded")
        mock_dispatch.assert_called_once()

    def test_complete_direct_upload_rejects_size_mismatch(self) -> None:
        job_id = uuid4()
        payload = b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42isom"
        fake_job = MagicMock(
            id=job_id,
            created_at=datetime.now(timezone.utc),
            status="uploading",
            source_video_url="https://storage.example/public/uploads/test.mp4?cm_expected_size=999",
        )

        def fake_download(source_url: str, target_path) -> object:
            target_path.write_bytes(payload)
            return target_path

        with (
            patch("api.routes.upload.get_job", return_value=fake_job),
            patch("api.routes.upload.storage_service.extract_object_path", return_value="uploads/test.mp4"),
            patch("api.routes.upload.storage_service.object_exists", return_value=True),
            patch("api.routes.upload.storage_service.download_to_local", side_effect=fake_download),
            patch("api.routes.upload.update_job") as mock_update_job,
            patch("api.routes.upload.dispatch_task") as mock_dispatch,
        ):
            response = complete_direct_upload(DirectUploadCompleteRequest(job_id=str(job_id)))

        self.assertEqual(response.status_code, 400)
        self.assertIn("upload_verification_failed", response.body.decode("utf-8"))
        mock_update_job.assert_called_once()
        mock_dispatch.assert_not_called()

    def test_complete_direct_upload_rejects_expired_session(self) -> None:
        job_id = uuid4()
        fake_job = MagicMock(
            id=job_id,
            created_at=datetime.now(timezone.utc),
            status="failed",
            source_video_url="https://storage.example/public/uploads/test.mp4?cm_expected_size=24",
        )

        with (
            patch("api.routes.upload.get_job", return_value=fake_job),
            patch("api.routes.upload.update_job") as mock_update_job,
            patch("api.routes.upload.dispatch_task") as mock_dispatch,
        ):
            response = complete_direct_upload(DirectUploadCompleteRequest(job_id=str(job_id)))

        self.assertEqual(response.status_code, 409)
        self.assertIn("upload_session_expired", response.body.decode("utf-8"))
        mock_update_job.assert_not_called()
        mock_dispatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
