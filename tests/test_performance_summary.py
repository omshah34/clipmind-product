"""Tests for performance summary contract helpers."""

import unittest
from datetime import datetime, timezone

from db.repositories.performance import build_performance_summary


class PerformanceSummaryTests(unittest.TestCase):
    def test_build_performance_summary_includes_chart_points_and_top_clips(self) -> None:
        rows = [
            {
                "job_id": "11111111-1111-1111-1111-111111111111",
                "platform": "youtube",
                "views": 100,
                "likes": 10,
                "saves": 4,
                "shares": 2,
                "comments": 1,
                "engagement_score": 0.17,
                "completion_rate": 0.5,
                "ai_predicted_score": 0.1,
                "clip_index": 0,
                "milestone_tier": "validated",
                "window_complete": True,
                "source_type": "real",
                "synced_at": datetime.now(timezone.utc),
            }
        ]
        summary = build_performance_summary(
            job_id="11111111-1111-1111-1111-111111111111",
            rows=rows,
            top_clips=[
                {
                    "clip_index": 0,
                    "clip_url": "https://example.com/clip.mp4",
                    "duration": 12.5,
                    "final_score": 9.8,
                    "reason": "Strong hook",
                }
            ],
            latest_job_id="11111111-1111-1111-1111-111111111111",
            data_source="real",
        )

        self.assertEqual(summary["total_views"], 100)
        self.assertEqual(summary["total_saves"], 4)
        self.assertEqual(summary["platform_stats"][0]["total_clips"], 1)
        self.assertEqual(summary["all_clips_performance"][0]["predicted"], 0.1)
        self.assertEqual(summary["top_clips"][0]["final_score"], 9.8)


if __name__ == "__main__":
    unittest.main()
