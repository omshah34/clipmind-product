"""File: tests/test_dna_intelligence.py
Purpose: Test DNA Intelligence services, triggers, and transparency.
"""

import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import services
from services.dna.insight_reporter import InsightReporter
from services.dna.content_advisor import ContentAdvisor

# Force import of workers submodules to help patcher
import workers.track_signals

class TestDNAIntelligence(unittest.TestCase):

    def setUp(self):
        self.reporter = InsightReporter()
        self.advisor = ContentAdvisor()

    def test_confidence_ratings(self):
        """Verify trust levels based on signal sample size."""
        self.assertEqual(self.reporter.calculate_confidence(0)["label"], "Insufficient")
        self.assertEqual(self.reporter.calculate_confidence(10)["label"], "Initial")
        self.assertEqual(self.reporter.calculate_confidence(30)["label"], "Emerging")
        self.assertEqual(self.reporter.calculate_confidence(200)["label"], "Rock-Solid")

    def test_shift_report_generation(self):
        """Verify human-readable factual reporting."""
        report = self.reporter.generate_shift_report("hook_weight", 1.0, 1.25, 20)
        self.assertIn("Hook", report)
        self.assertIn("increased by 25%", report)
        
        report_neg = self.reporter.generate_shift_report("story_weight", 1.0, 0.5, 20)
        self.assertIn("Story", report_neg)
        self.assertIn("decreased by 50%", report_neg)

    def test_advisor_trigger_logic(self):
        """Verify rule-based proactive advice triggers."""
        # Case 1: Underutilized
        weights = {"hook": 0.5, "story": 1.5}
        signals = {"publish": 1, "download": 1, "skip": 8} # 10 total
        recs = self.advisor.get_recommendations(weights, signals, "Initial")
        
        recs_ids = [r["id"] for r in recs]
        self.assertIn("underutilized_hook", recs_ids)
        self.assertIn("dominant_story", recs_ids)

        # Case 2: Insufficient Data
        recs_low = self.advisor.get_recommendations(weights, {"publish": 2}, "Insufficient")
        self.assertEqual(recs_low[0]["id"], "insufficient_data")

    @patch("services.dna.insight_reporter.log_dna_shift")
    @patch("workers.track_signals.get_user_score_weights")
    @patch("workers.track_signals.get_user_signals")
    @patch("workers.track_signals.update_user_score_weights")
    def test_worker_logging_integration(self, mock_update, mock_get_signals, mock_get_weights, mock_log_shift):
        """Verify that the worker logs shifts > 0.05."""
        from workers.track_signals import aggregate_user_signals
        
        # Setup: old weights at 1.0, new weights calculated at 1.2
        mock_get_weights.return_value = {"weights": {"hook": 1.0}}
        mock_get_signals.return_value = [{"signal_type": "published"}] * 10
        
        # Trigger aggregation
        with patch("workers.track_signals.calculate_optimal_weights") as mock_calc:
            mock_calc.return_value = {"hook": 1.2, "story": 1.0}
            aggregate_user_signals("00000000-0000-0000-0000-000000000000", recalculate_weights=True)
            
            # Check if log_dna_shift was called for 'hook' (diff 0.2 > 0.05)
            # but NOT for 'story' (diff 0.0)
            log_calls = [call.kwargs.get("dimension") for call in mock_log_shift.call_args_list]
            self.assertIn("hook", log_calls)
            self.assertNotIn("story", log_calls)

if __name__ == "__main__":
    unittest.main()
