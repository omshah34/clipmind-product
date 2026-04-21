"""File: tests/test_jobs.py
Purpose: Test job status responses and clip details retrieval API endpoints.
"""

import unittest
import uuid
from datetime import datetime, timezone

from api.models.job import ClipResult, JobRecord
from api.routes.jobs import build_clip_summaries


class JobRouteTests(unittest.TestCase):
    def test_completed_job_returns_clip_summaries(self) -> None:
        job = JobRecord(
            id=uuid.uuid4(),
            status="completed",
            source_video_url="file:///video.mp4",
            clips_json=[
                ClipResult(
                    clip_index=1,
                    start_time=10.0,
                    end_time=42.0,
                    duration=32.0,
                    clip_url="https://example.com/clip.mp4",
                    hook_score=8.0,
                    emotion_score=7.5,
                    clarity_score=8.5,
                    story_score=7.0,
                    virality_score=7.2,
                    final_score=7.81,
                    reason="Strong hook and clear payoff.",
                )
            ],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        summaries = build_clip_summaries(job)

        self.assertIsNotNone(summaries)
        self.assertEqual(len(summaries or []), 1)
        self.assertEqual((summaries or [])[0].clip_index, 1)


if __name__ == "__main__":
    unittest.main()
