"""Tests for Redis-safe task dispatching."""

import unittest
from unittest.mock import MagicMock, patch

from services.event_emitter import emit_event
from services.task_queue import dispatch_task


class TaskQueueTests(unittest.TestCase):
    def test_dispatch_task_uses_celery_when_dispatch_succeeds(self) -> None:
        task = MagicMock()
        task.delay.return_value = "queued"

        result = dispatch_task(task, "job-123", task_name="demo.task")

        self.assertEqual(result, "queued")
        task.delay.assert_called_once_with("job-123")

    def test_dispatch_task_runs_inline_fallback_when_dispatch_fails(self) -> None:
        task = MagicMock()
        task.delay.side_effect = RuntimeError("broker down")
        fallback = MagicMock(return_value="inline")

        result = dispatch_task(
            task,
            "job-123",
            fallback=fallback,
            task_name="demo.task",
        )

        self.assertEqual(result, "inline")
        fallback.assert_called_once_with("job-123")
        task.delay.assert_called_once_with("job-123")

    def test_dispatch_task_resolves_registered_task_names(self) -> None:
        task = MagicMock()
        task.delay.return_value = "queued"

        with patch("workers.celery_app.celery_app.tasks.get", return_value=task) as mock_get:
            result = dispatch_task("workers.pipeline.process_job", "job-123", task_name="demo.task")

        self.assertEqual(result, "queued")
        mock_get.assert_called_once_with("workers.pipeline.process_job")
        task.delay.assert_called_once_with("job-123")

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
