"""File: tests/test_production_guardrails.py
Purpose: Test Rate Limiting and Deep Health checks.
"""

import unittest
import os
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from api.main import app

class TestProductionGuardrails(unittest.TestCase):

    def setUp(self):
        # We need to make sure ENVIRONMENT is set so /health tries to ping workers if needed,
        # but here we mostly want to verify the middleware doesn't crash.
        self.client = TestClient(app)

    @patch("api.main.os.getenv")
    def test_health_endpoint_healthy(self, mock_getenv):
        """Verify /health returns 200 when all dependencies are up."""
        mock_getenv.return_value = "development"
        
        with patch("db.connection.engine.connect") as mock_conn:
            with patch("workers.celery_app.celery_app.connection_or_acquire") as mock_redis:
                response = self.client.get("/health")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["status"], "ok")

    @patch("api.main.os.getenv")
    def test_health_endpoint_unhealthy_db(self, mock_getenv):
        """Verify /health returns 503 when DB is down."""
        mock_getenv.return_value = "development"
        
        with patch("db.connection.engine.connect", side_effect=Exception("DB Down")):
            response = self.client.get("/health")
            self.assertEqual(response.status_code, 503)

    @patch("api.middleware.rate_limiter.SlidingWindowRateLimiter.get_redis")
    def test_rate_limiter_sliding_window(self, mock_get_redis):
        """Verify the sliding window LUA script logic (mocked)."""
        mock_redis = AsyncMock()
        # Evaluate atomic script results: [count, allowed]
        mock_redis.evalsha = AsyncMock(return_value=[5, 1])
        mock_get_redis.return_value = mock_redis
        
        # Test a valid path: /api/v1/jobs/{uuid}/status
        # We use a dummy UUID
        response = self.client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/status")
        # In test env without DB, this might be 404 or 401, but we want to see it pass the Middleware
        # Middleware returns 429 if blocked, or proceeds.
        self.assertNotEqual(response.status_code, 429)

        # Now mock a denial
        mock_redis.evalsha.return_value = [100, 0]
        response_denied = self.client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/status")
        self.assertEqual(response_denied.status_code, 429)

    def test_rate_limiter_fail_open(self):
        """Verify that the rate limiter fails OPEN if Redis is down."""
        # Force get_redis to fail
        with patch("api.middleware.rate_limiter.SlidingWindowRateLimiter.get_redis", side_effect=Exception("Redis Dead")):
            response = self.client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/status")
            # Should NOT be 500 or 429. Likely 401/404 depending on auth/db state, which is fine (Fail-Open)
            self.assertNotEqual(response.status_code, 429)
            self.assertNotEqual(response.status_code, 500)

if __name__ == "__main__":
    unittest.main()
