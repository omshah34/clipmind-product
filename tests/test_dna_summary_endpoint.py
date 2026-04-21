"""File: tests/test_dna_summary_endpoint.py
Purpose: Test the /dna/summary API routes.
"""
import unittest
from fastapi.testclient import TestClient
from api.main import app
from unittest.mock import patch, MagicMock

class TestDNASummaryEndpoint(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.user_id = "00000000-0000-0000-0000-000000000000"

    @patch("api.routes.content_dna.get_latest_executive_summary")
    def test_get_summary_not_found(self, mock_get):
        """Verify 404 when no summary exists."""
        mock_get.return_value = None
        response = self.client.get("/api/v1/dna/summary")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No summary found", response.json()["detail"])

    @patch("api.routes.content_dna.get_latest_executive_summary")
    def test_get_summary_success(self, mock_get):
        """Verify 200 when summary exists."""
        mock_get.return_value = {
            "id": "sum123",
            "summary_text": "Strategic Analysis: Test summary",
            "created_at": "2026-04-16T12:00:00"
        }
        response = self.client.get("/api/v1/dna/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], "sum123")

    @patch("api.routes.content_dna.trigger_summary_task.delay")
    def test_post_generate_summary(self, mock_delay):
        """Verify task triggering."""
        mock_task = MagicMock()
        mock_task.id = "task_uuid_123"
        mock_delay.return_value = mock_task
        
        response = self.client.post("/api/v1/dna/summary/generate")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "accepted")
        self.assertEqual(response.json()["task_id"], "task_uuid_123")

if __name__ == "__main__":
    unittest.main()
