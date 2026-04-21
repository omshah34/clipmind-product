"""Tests for Redis-safe task dispatching."""

import unittest
from unittest.mock import MagicMock, patch

from services.event_emitter import emit_event
from services.task_queue import dispatch_task


class TaskQueueTests(unittest.TestCase):
    def test_dispatch_task_uses_celery_when_redis_is_available(self) -> None:
        task = MagicMock()
        task.delay.return_value = "queued"

        with patch("services.task_queue.is_redis_available", return_value=True):
            result = dispatch_task(task, "job-123", task_name="demo.task")

        self.assertEqual(result, "queued")
        task.delay.assert_called_once_with("job-123")

    def test_dispatch_task_runs_inline_fallback_when_redis_is_down(self) -> None:
        task = MagicMock()
        fallback = MagicMock(return_value="inline")

        with patch("services.task_queue.is_redis_available", return_value=False):
            result = dispatch_task(
                task,
                "job-123",
                fallback=fallback,
                task_name="demo.task",
            )

        self.assertEqual(result, "inline")
        fallback.assert_called_once_with("job-123")
        task.delay.assert_not_called()

    def test_event_emitter_skips_when_redis_is_down(self) -> None:
        with (
            patch("services.event_emitter.is_redis_available", return_value=False),
            patch("services.event_emitter.logger.warning") as mock_warning,
        ):
            emit_event(
                event_type="job.completed",
                event_data={"job_id": "123"},
                user_id="user-123",
            )

        mock_warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
