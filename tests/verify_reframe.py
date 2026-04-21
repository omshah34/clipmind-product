"""File: tests/verify_reframe.py
Purpose: Unit tests and verification for Phase 1: AI Auto-Reframing (Tasks API).
"""

import sys
import os
import unittest
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.subject_tracking import SubjectTracker

class TestAutoReframe(unittest.TestCase):
    @patch("services.subject_tracking.ensure_model_exists")
    @patch("services.subject_tracking.vision.FaceDetector.create_from_options")
    def setUp(self, mock_create, mock_ensure):
        self.mock_detector = MagicMock()
        mock_create.return_value = self.mock_detector
        # Avoid downloading model during unit test setup
        self.tracker = SubjectTracker(sample_rate_fps=2)

    def test_tracker_no_file(self):
        """Should raise FileNotFoundError if video doesn't exist."""
        with self.assertRaises(FileNotFoundError):
            self.tracker.get_optimal_crop_x(Path("/tmp/non_existent.mp4"))

    @patch("services.subject_tracking.Path.exists")
    @patch("cv2.VideoCapture")
    def test_tracker_no_subjects(self, mock_vc, mock_exists):
        """Should return None if no faces are detected in sampled frames."""
        mock_exists.return_value = True
        mock_cap = mock_vc.return_value
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            0: 30.0, # FPS
            7: 60,   # Total Frames
            3: 1920, # Width
            4: 1080  # Height
        }.get(prop, 0)
        
        # Simulate 60 frames (numpy arrays), no detections
        mock_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [(True, mock_frame)] * 60 + [(False, None)]
        
        self.mock_detector.detect.return_value.detections = []
        
        result = self.tracker.get_optimal_crop_x(Path("dummy.mp4"))
        self.assertIsNone(result)

    @patch("services.subject_tracking.Path.exists")
    @patch("cv2.VideoCapture")
    @patch("mediapipe.Image")
    def test_tracker_clamping(self, mock_mp_img, mock_vc, mock_exists):
        """Should return a clamped X coordinate even if subject is at the extreme edge."""
        mock_exists.return_value = True
        mock_cap = mock_vc.return_value
        mock_cap.isOpened.return_value = True
        mock_cap.get.side_effect = lambda prop: {
            1: 0,    # Pos
            3: 1920, # Width
            4: 1080, # Height
            5: 30.0, # FPS
            7: 30    # Total Frames
        }.get(prop, 0)
        
        # Simulate 1 frame read
        mock_frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        mock_cap.read.side_effect = [(True, mock_frame), (False, None)]
        
        # Mock detection at the very left edge (x_center = 50px)
        mock_detection = MagicMock()
        mock_detection.bounding_box.origin_x = 0
        mock_detection.bounding_box.width = 100
        mock_detection.bounding_box.height = 100
        
        self.mock_detector.detect.return_value.detections = [mock_detection]
        
        # width=1920, height=1080
        # target_w = 1080 * 9/16 = 607.5
        # half_w = 303.75
        # Result at 50px but Clamped X should be at least 303.75
        
        result = self.tracker.get_optimal_crop_x(Path("dummy.mp4"))
        print(f"Clamped X result: {result}")
        self.assertGreaterEqual(result, 303.75)
        self.assertLessEqual(result, 1920 - 303.75)

    def test_video_processor_filter_with_crop(self):
        """Should generate correct FFmpeg filter string when crop_x is provided."""
        from services.video_processor import build_subtitle_filter
        srt_path = Path("fake.srt")
        crop_x = 500.5
        
        vf = build_subtitle_filter(
            srt_path=srt_path,
            input_width=1920,
            input_height=1080,
            crop_x=crop_x
        )
        
        print(f"Generated VF: {vf}")
        self.assertIn("crop=ih*9/16:ih:500.5-(ih*9/16/2):0", vf)

if __name__ == "__main__":
    unittest.main()
