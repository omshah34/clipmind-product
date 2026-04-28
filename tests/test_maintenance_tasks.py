"""Tests for maintenance task cleanup behavior."""

import unittest
from unittest.mock import MagicMock, patch

from workers.maintenance_tasks import check_worker_health, reclaim_stale_jobs


class MaintenanceTaskTests(unittest.TestCase):
    def test_reclaim_stale_jobs_includes_uploading(self) -> None:
        mock_engine = MagicMock()
        mock_engine.dialect.name = "postgresql"
        mock_connection = MagicMock()
        result = MagicMock()
        result.all.return_value = [(1,)]
        mock_connection.execute.return_value = result
        mock_engine.begin.return_value.__enter__.return_value = mock_connection

        with patch("db.connection.engine", mock_engine):
            count = reclaim_stale_jobs()

        self.assertEqual(count, 1)
        sql_text = str(mock_connection.execute.call_args.args[0])
        self.assertIn("uploading", sql_text)

    def test_check_worker_health_treats_ping_miss_with_stats_as_transient(self) -> None:
        first_inspector = MagicMock()
        first_inspector.ping.return_value = None

        second_inspector = MagicMock()
        second_inspector.ping.return_value = None

        stats_inspector = MagicMock()
        stats_inspector.stats.return_value = {"celery@worker1": {"pid": 123}}

        with patch("workers.maintenance_tasks.celery_app.control.inspect", side_effect=[first_inspector, second_inspector, stats_inspector]):
            result = check_worker_health()

        self.assertEqual(result["status"], "degraded")
        self.assertEqual(result["workers_online"], 1)
        self.assertEqual(result["reason"], "ping_transient")

    def test_check_worker_health_is_degraded_locally_when_no_workers_respond(self) -> None:
        first_inspector = MagicMock()
        first_inspector.ping.return_value = None

        second_inspector = MagicMock()
        second_inspector.ping.return_value = None

        stats_inspector = MagicMock()
        stats_inspector.stats.return_value = None

        with patch("workers.maintenance_tasks.celery_app.control.inspect", side_effect=[first_inspector, second_inspector, stats_inspector]):
            result = check_worker_health()

        self.assertEqual(result, {"status": "degraded", "reason": "no_workers_local"})

    def test_check_worker_health_is_critical_in_production_when_no_workers_respond(self) -> None:
        first_inspector = MagicMock()
        first_inspector.ping.return_value = None

        second_inspector = MagicMock()
        second_inspector.ping.return_value = None

        stats_inspector = MagicMock()
        stats_inspector.stats.return_value = None

        with patch("workers.maintenance_tasks.celery_app.control.inspect", side_effect=[first_inspector, second_inspector, stats_inspector]):
            with patch("workers.maintenance_tasks.os.getenv", return_value="production"):
                with patch("workers.maintenance_tasks.platform.system", return_value="Linux"):
                    result = check_worker_health()

        self.assertEqual(result, {"status": "critical", "reason": "no_workers"})


if __name__ == "__main__":
    unittest.main()
