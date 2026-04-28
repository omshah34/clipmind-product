import unittest
from unittest.mock import MagicMock, patch
from workers.source_poller import poll_all_sources

class TestSourcePoller(unittest.TestCase):
    
    @patch("workers.source_poller.list_active_sources_for_polling")
    @patch("workers.source_poller.get_source_ingestion_service")
    @patch("workers.source_poller.RobustRedisLock")
    @patch("workers.source_poller.redis")
    @patch("workers.source_poller.settings")
    def test_poll_all_sources_concurrency(self, mock_settings, mock_redis, mock_lock_cls, mock_get_ingestion, mock_list_sources):
        # Setup
        mock_settings.poller_max_workers = 3
        mock_settings.redis_url = "redis://localhost"
        
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_lock.__enter__.return_value = mock_lock
        mock_lock.__enter__.side_effect = lambda: (mock_lock.acquire(), mock_lock)[1]
        mock_lock_cls.return_value = mock_lock
        
        mock_list_sources.return_value = [
            {"id": "source1"}, {"id": "source2"}, {"id": "source3"}, {"id": "source4"}
        ]
        
        mock_ingestion = MagicMock()
        # Simulate some delay and then return number of jobs
        mock_ingestion.poll_source.side_effect = lambda s: 1
        mock_get_ingestion.return_value = mock_ingestion
        
        # Execute
        result = poll_all_sources()
        
        # Verify
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sources_polled"], 4)
        self.assertEqual(result["new_jobs_triggered"], 4)
        
        # Verify poll_source was called for each source
        self.assertEqual(mock_ingestion.poll_source.call_count, 4)

    @patch("workers.source_poller.list_active_sources_for_polling")
    @patch("workers.source_poller.get_source_ingestion_service")
    @patch("workers.source_poller.RobustRedisLock")
    @patch("workers.source_poller.redis")
    @patch("workers.source_poller.settings")
    def test_poll_all_sources_exception_isolation(self, mock_settings, mock_redis, mock_lock_cls, mock_get_ingestion, mock_list_sources):
        # Setup
        mock_settings.poller_max_workers = 2
        
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_lock.__enter__.return_value = mock_lock
        mock_lock.__enter__.side_effect = lambda: (mock_lock.acquire(), mock_lock)[1]
        mock_lock_cls.return_value = mock_lock
        
        mock_list_sources.return_value = [
            {"id": "source_ok"}, {"id": "source_fail"}
        ]
        
        mock_ingestion = MagicMock()
        def mock_poll(source):
            if source["id"] == "source_fail":
                raise Exception("Network Error")
            return 1
        
        mock_ingestion.poll_source.side_effect = mock_poll
        mock_get_ingestion.return_value = mock_ingestion
        
        # Execute
        result = poll_all_sources()
        
        # Verify
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["sources_polled"], 2)
        # Only one job triggered because the other failed
        self.assertEqual(result["new_jobs_triggered"], 1)
        
        # Verify poller finished even with an exception in one source
        self.assertEqual(result["status"], "success")

if __name__ == "__main__":
    unittest.main()
