"""Tests for Batch Export Engine."""

import pytest
from services.batch_service import BatchService

def test_batch_trigger_concurrency():
    service = BatchService()
    # Request 10 jobs, but the guard should limit to 3 (config spec)
    job_ids = [f"job-{i}" for i in range(10)]
    
    # Mocking celery send_task to avoid hitting Redis
    import unittest.mock as mock
    with mock.patch("services.batch_service.celery_app.send_task") as mock_send_task:
        enqueued_count = service.trigger_batch_render(job_ids)
        assert enqueued_count == service.MAX_CONCURRENT_BATCH_JOBS
        assert mock_send_task.call_count == service.MAX_CONCURRENT_BATCH_JOBS

def test_batch_zip_bundling():
    service = BatchService()
    import unittest.mock as mock
    from pathlib import Path
    
    # Mocking get_job and clip existence
    with mock.patch("services.export_engine.get_job") as mock_get_job:
        mock_get_job.return_value = mock.Mock(
            clips_json=[{"clip_index": 0, "clip_url": "file:///tmp/clip0.mp4"}]
        )
        
        # Mocking Path.exists for the clip
        with mock.patch("pathlib.Path.exists") as mock_exists:
            mock_exists.return_value = True
            with mock.patch("zipfile.ZipFile") as mock_zip:
                zip_path = service.create_batch_zip(["job-1"])
                assert zip_path.suffix == ".zip"
                assert "batch" in zip_path.name
