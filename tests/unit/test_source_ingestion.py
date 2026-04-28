import unittest
from unittest.mock import MagicMock, patch
from services.source_ingestion import SourceIngestionService

class TestSourceIngestion(unittest.TestCase):
    def setUp(self):
        self.service = SourceIngestionService()
        self.mock_source = {
            "id": "test_source",
            "source_type": "rss_feed",
            "user_id": "user123",
            "config_json": {"feed_url": "http://example.com/rss"}
        }

    @patch("core.redis_utils.RobustRedisLock")
    @patch("redis.from_url")
    @patch("services.source_ingestion.update_source_status", create=True)
    @patch("services.source_ingestion.SourceIngestionService._poll_rss")
    @patch("core.config.settings")
    def test_poll_source_acquires_correct_lock(self, mock_settings, mock_poll_rss, mock_update_status, mock_redis_url, mock_lock_cls):
        # Setup
        mock_settings.redis_url = "redis://localhost"
        mock_lock = MagicMock()
        mock_lock.acquire.return_value = True
        mock_lock.__enter__.return_value = mock_lock
        mock_lock_cls.return_value = mock_lock
        
        mock_poll_rss.return_value = []
        
        # Execute
        self.service.poll_source(self.mock_source)
        
        # Verify lock key
        mock_lock_cls.assert_called_once()
        args, kwargs = mock_lock_cls.call_args
        self.assertEqual(args[1], "lock:source:test_source")
        # Verify non-blocking
        blocking = kwargs.get("blocking")
        if blocking is None and len(args) > 4:
            blocking = args[4]
        self.assertFalse(blocking)

    @patch("core.redis_utils.RobustRedisLock")
    @patch("redis.from_url")
    @patch("services.source_ingestion.update_source_status", create=True)
    @patch("core.config.settings")
    def test_poll_source_skips_if_locked(self, mock_settings, mock_update_status, mock_redis_url, mock_lock_cls):
        # Setup
        mock_lock = MagicMock()
        # Simulate lock acquisition failure (RuntimeError in context manager)
        mock_lock.__enter__.side_effect = RuntimeError("Locked")
        mock_lock_cls.return_value = mock_lock
        
        # Execute
        result = self.service.poll_source(self.mock_source)
        
        # Verify
        self.assertEqual(result, 0)
        # Should not have called update_source_status with success=True
        for call in mock_update_status.call_args_list:
            self.assertFalse(call[1].get("success"))

if __name__ == "__main__":
    unittest.main()
