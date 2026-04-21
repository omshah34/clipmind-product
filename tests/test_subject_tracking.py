import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
from services.subject_tracking import SubjectTracker, get_optimal_crop_x

@patch("services.subject_tracking.cv2.VideoCapture")
@patch("services.subject_tracking.vision.FaceDetector.create_from_options")
@patch.object(Path, "exists", return_value=True)
@patch("services.subject_tracking.mp.Image")
@patch("services.subject_tracking.cv2.cvtColor")
def test_get_optimal_centers_padding(mock_color, mock_image, mock_exists, mock_detector, mock_video):
    # Mocking video capture
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = [30.0, 1920, 1080]
    # First call returns frame, second call returns ret=False to exit loop
    mock_cap.read.side_effect = [(True, np.zeros((1080, 1920, 3), dtype=np.uint8)), (False, None)]
    mock_video.return_value = mock_cap
    
    # Mocking detection result
    mock_det = MagicMock()
    mock_bbox = MagicMock()
    mock_bbox.origin_x = 450
    mock_bbox.width = 100
    mock_bbox.height = 100
    
    mock_detection = MagicMock()
    mock_detection.bounding_box = mock_bbox
    
    mock_det.detect.return_value.detections = [mock_detection]
    mock_detector.return_value = mock_det

    tracker = SubjectTracker()
    tracker.detector = mock_det
    
    centers = tracker.get_optimal_centers(Path("test.mp4"), count=2)
    
    assert len(centers) == 2
    assert centers[0] == 500.0
    assert centers[1] == 960.0

@patch.object(Path, "exists", return_value=True)
def test_get_optimal_crop_x_wrapper(mock_exists):
    with patch("services.subject_tracking.SubjectTracker.get_optimal_centers") as mock_centers:
        mock_centers.return_value = [777.0]
        x = get_optimal_crop_x(Path("test.mp4"))
        assert x == 777.0

@patch("services.subject_tracking.cv2.VideoCapture")
@patch.object(Path, "exists", return_value=True)
@patch("services.subject_tracking.mp.Image")
@patch("services.subject_tracking.cv2.cvtColor")
@patch("services.subject_tracking.vision.FaceDetector.create_from_options")
def test_no_faces_detected_fallback(mock_detector, mock_color, mock_image, mock_exists, mock_video):
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    mock_cap.get.side_effect = [30.0, 1280, 720]
    mock_cap.read.side_effect = [(True, np.zeros((720, 1280, 3), dtype=np.uint8)), (False, None)]
    mock_video.return_value = mock_cap
    
    mock_det = MagicMock()
    mock_det.detect.return_value.detections = []
    mock_detector.return_value = mock_det

    tracker = SubjectTracker()
    tracker.detector = mock_det
    
    centers = tracker.get_optimal_centers(Path("test.mp4"), count=2)
    assert centers == [640.0, 640.0]
