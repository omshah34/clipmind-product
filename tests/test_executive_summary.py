"""File: tests/test_executive_summary.py
Purpose: Test the ExecutiveSummarizer service and persistence.
"""
import unittest
import asyncio
from unittest.mock import AsyncMock, patch
from services.dna.executive_summarizer import ExecutiveSummarizer
from db.queries import get_latest_executive_summary

class TestExecutiveSummary(unittest.TestCase):

    def setUp(self):
        self.user_id = "00000000-0000-0000-0000-000000000000"
        self.summarizer = ExecutiveSummarizer(api_key="test_key")

    @patch("services.dna.executive_summarizer.get_dna_logs_for_summary")
    @patch("services.dna.executive_summarizer.httpx.AsyncClient.post")
    def test_generate_summary_success(self, mock_post, mock_get_logs):
        """Verify LLM synthesis and database persistence."""
        # 1. Mock Logs
        mock_get_logs.return_value = [
            {"id": "log1", "log_type": "weight_shift", "dimension": "hook", "old_value": 1.0, "new_value": 1.5, "reasoning_code": "high_engagement", "created_at": MagicMock()},
            {"id": "log2", "log_type": "milestone", "dimension": "emotion", "old_value": None, "new_value": None, "reasoning_code": "converging", "created_at": MagicMock()},
        ]

        # 2. Mock LLM Response
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "Strategic Analysis: Your audience is pivoting toward high-hook content."}}]
        }
        mock_post.return_value = mock_resp

        # 3. Run Synthesis
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self.summarizer.generate_summary(self.user_id))

        # 4. Assertions
        self.assertIsNotNone(result)
        self.assertIn("Strategic Analysis", result["summary_text"])
        self.assertEqual(result["user_id"], self.user_id)
        
        # Verify it can be fetched back
        fetched = get_latest_executive_summary(self.user_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["id"], result["id"])

    @patch("services.dna.executive_summarizer.get_dna_logs_for_summary")
    def test_generate_summary_no_logs(self, mock_get_logs):
        """Verify it returns None if no logs exist in window."""
        mock_get_logs.return_value = []
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(self.summarizer.generate_summary(self.user_id))
        self.assertIsNone(result)

from unittest.mock import MagicMock
if __name__ == "__main__":
    unittest.main()
