"""File: tests/test_source_poller.py
Purpose: Test the Channel Watchdog (Phase 2) polling and deduplication logic.
"""

import unittest
from unittest.mock import MagicMock, patch
from workers.source_poller import poll_all_sources, POLLER_LOCK_KEY

class TestSourcePoller(unittest.TestCase):

    def setUp(self):
        # Mock Redis
        self.mock_redis = MagicMock()
        
        # Mock DB queries
        self.mock_sources = [
            {
                "id": "src_123",
                "user_id": "user_456",
                "source_type": "youtube_channel",
                "config_json": {"channel_url": "https://youtube.com/c/test"}
            }
        ]

    @patch("workers.source_poller.celery_app")
    @patch("workers.source_poller.list_active_sources_for_polling")
    @patch("workers.source_poller.get_source_ingestion_service")
    def test_locking_mechanism(self, mock_get_service, mock_list_sources, mock_celery):
        """Should skip polling if lock is already held."""
        mock_celery.backend.client = self.mock_redis
        
        # Simulate lock held by another process
        self.mock_redis.set.return_value = False
        
        result = poll_all_sources()
        
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "lock_active")
        self.mock_redis.set.assert_called_with(POLLER_LOCK_KEY, "locked", ex=1800, nx=True)
        # Should NOT call DB or Service
        mock_list_sources.assert_not_called()

    @patch("workers.source_poller.celery_app")
    @patch("workers.source_poller.list_active_sources_for_polling")
    @patch("workers.source_poller.get_source_ingestion_service")
    def test_deduplication_and_ingestion(self, mock_get_service, mock_list_sources, mock_celery):
        """Should only trigger jobs for new, unprocessed videos."""
        mock_celery.backend.client = self.mock_redis
        self.mock_redis.set.return_value = True
        
        mock_list_sources.return_value = self.mock_sources
        
        # Mock Ingestion Service
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        # Simulate finding 2 new videos (but service handles dedup internally now)
        mock_service.poll_source.return_value = 2
        
        result = poll_all_sources()
        
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["new_jobs_triggered"], 2)
        
        # Verify lock was released
        self.mock_redis.delete.assert_called_with(POLLER_LOCK_KEY)

    @patch("services.source_ingestion.is_video_processed")
    @patch("services.source_ingestion.record_ingestion_atomic")
    @patch("services.source_ingestion.dispatch_task")
    @patch("services.source_ingestion.subprocess.run")
    def test_ingestion_service_dedup(self, mock_run, mock_dispatch, mock_atomic, mock_is_processed):
        """Test that the service correctly filters processed videos."""
        from services.source_ingestion import SourceIngestionService
        
        # Mock yt-dlp outputting 2 videos
        mock_run.return_value.stdout = "vid_1\nvid_2\n"
        
        # Mock vid_1 as already processed, vid_2 as new
        mock_is_processed.side_effect = lambda sid, vid: vid == "vid_1"
        mock_atomic.return_value = "job_new"
        
        service = SourceIngestionService()
        source = self.mock_sources[0]
        
        new_jobs = service.poll_source(source)
        
        self.assertEqual(new_jobs, 1) # Only vid_2 was new
        mock_atomic.assert_called_once() # Only called for vid_2
        mock_dispatch.assert_called_once_with("workers.pipeline.process_job", job_id="job_new")

if __name__ == "__main__":
    unittest.main()
