"""File: services/subject_tracking.py
Purpose: AI-powered subject detection and reframing logic. 
         Uses modern Mediapipe Tasks API to find the best 'static anchor' 
         for vertical 9:16 crops in horizontal videos.
"""

import logging
import os
import hashlib
import shutil
import time
from pathlib import Path
import urllib.request
from dataclasses import dataclass
from types import SimpleNamespace
from typing import List, Tuple, Optional

try:
    import cv2
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    cv2 = SimpleNamespace(
        VideoCapture=None,
        COLOR_BGR2RGB=4,
        CAP_PROP_FPS=5,
        CAP_PROP_FRAME_WIDTH=3,
        CAP_PROP_FRAME_HEIGHT=4,
        cvtColor=lambda frame, code: frame,
    )

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    class _DummyImageFormat:
        SRGB = "SRGB"

    class _DummyImage:
        def __init__(self, image_format=None, data=None):
            self.image_format = image_format
            self.data = data

    class _DummyFaceDetectorOptions:
        def __init__(self, base_options=None):
            self.base_options = base_options

    class _DummyFaceDetector:
        @staticmethod
        def create_from_options(options):
            return SimpleNamespace(detect=lambda image: SimpleNamespace(detections=[]))

    mp = SimpleNamespace(Image=_DummyImage, ImageFormat=_DummyImageFormat)
    python = SimpleNamespace(BaseOptions=lambda model_asset_path=None: SimpleNamespace(model_asset_path=model_asset_path))
    vision = SimpleNamespace(FaceDetectorOptions=_DummyFaceDetectorOptions, FaceDetector=_DummyFaceDetector)

try:
    import numpy as np
except ModuleNotFoundError:  # pragma: no cover - local fallback for tests
    class _MiniNumpy:
        uint8 = int

        @staticmethod
        def zeros(shape, dtype=None):
            if not shape:
                return 0
            size = int(shape[0])
            remainder = tuple(shape[1:])
            return [_MiniNumpy.zeros(remainder, dtype=dtype) for _ in range(size)]

        @staticmethod
        def median(values):
            ordered = sorted(values)
            if not ordered:
                return 0.0
            mid = len(ordered) // 2
            if len(ordered) % 2:
                return float(ordered[mid])
            return float((ordered[mid - 1] + ordered[mid]) / 2)

    np = _MiniNumpy()

logger = logging.getLogger(__name__)

# Model configuration
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/latest/blaze_face_short_range.tflite"
MODEL_PATH = Path(__file__).parent / "models" / "blaze_face_short_range.tflite"


def _verify_model_checksum(path: Path) -> None:
    expected = settings.subject_tracking_model_sha256.strip()
    if not expected:
        return

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise TrackingError(
            f"Face detector checksum mismatch for {path.name}: expected {expected[:12]}…, got {actual[:12]}…"
        )


def _copy_mirror_model() -> bool:
    mirror = settings.subject_tracking_model_mirror.strip()
    if not mirror:
        return False

    mirror_path = Path(mirror)
    if not mirror_path.exists():
        return False

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(mirror_path, MODEL_PATH)
    _verify_model_checksum(MODEL_PATH)
    logger.info("[tracking] Loaded face detection model from mirror: %s", mirror_path)
    return True

def ensure_model_exists():
    """Downloads the Mediapipe TFLite model if not present."""
    if MODEL_PATH.exists():
        try:
            _verify_model_checksum(MODEL_PATH)
            return
        except TrackingError:
            if _copy_mirror_model():
                logger.warning("[tracking] Replaced corrupted local model with mirror copy.")
                return
            raise

    if _copy_mirror_model():
        return

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = MODEL_PATH.with_suffix(".download")
    logger.info("[tracking] Downloading face detection model: %s", MODEL_URL)
    try:
        urllib.request.urlretrieve(MODEL_URL, str(temp_path))
        os.replace(temp_path, MODEL_PATH)
        _verify_model_checksum(MODEL_PATH)
        logger.info("[tracking] Model download complete.")
    except Exception:
        temp_path.unlink(missing_ok=True)
        if _copy_mirror_model():
            logger.warning("[tracking] Network download failed, used local mirror instead.")
            return
        raise

class TrackingError(RuntimeError):
    """Raised when subject tracking fails due to file or detection issues."""


@dataclass
class TrackingAnalysis:
    centers: List[float]
    detected_face_count: int
    primary_face_area_ratio: float | None
    frame_width: int
    frame_height: int

class SubjectTracker:
    def __init__(self, sample_rate_fps: int = 2):
        self.sample_rate_fps = sample_rate_fps
        self.enabled = callable(getattr(cv2, "VideoCapture", None))
        self.detector = None
        if not self.enabled:
            logger.info("[tracking] OpenCV is not installed; subject tracking disabled.")
            return

        ensure_model_exists()

        # Initialize the Face Detector
        base_options = python.BaseOptions(model_asset_path=str(MODEL_PATH))
        options = vision.FaceDetectorOptions(base_options=base_options)
        self.detector = vision.FaceDetector.create_from_options(options)

    def analyze_subjects(self, video_path: Path, count: int = 1, timeout_seconds: float = 120.0) -> TrackingAnalysis:
        """Analyze the clip and return center positions plus simple face-size heuristics."""
        if not self.enabled or self.detector is None:
            return TrackingAnalysis(
                centers=[],
                detected_face_count=0,
                primary_face_area_ratio=None,
                frame_width=0,
                frame_height=0,
            )

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(str(video_path))
        if cap is None:
            raise TrackingError("OpenCV VideoCapture returned None.")
        if not cap.isOpened():
            raise TrackingError(f"Could not open video file for tracking: {video_path}")

        fps = cap.get(cv2.CAP_PROP_FPS) or float(self.sample_rate_fps)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        next_sample_ms = 0.0
        started_at = time.monotonic()
        
        # List of lists, one per detected face index
        face_x_histories: List[List[float]] = [[] for _ in range(count)]
        primary_face_area_ratios: List[float] = []
        
        logger.info("[tracking] Analyzing up to %d subject positions in %s...", count, video_path.name)
        
        frame_idx = 0
        while cap.isOpened():
            if time.monotonic() - started_at > timeout_seconds:
                cap.release()
                raise TrackingError(f"Subject tracking timed out after {timeout_seconds:.0f}s for {video_path.name}")

            ret, frame = cap.read()
            if not ret:
                break
                
            current_ms = float(cap.get(cv2.CAP_PROP_POS_MSEC) or ((frame_idx / fps) * 1000.0 if fps > 0 else frame_idx * 500.0))
            if current_ms + 0.5 >= next_sample_ms:
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                
                detection_result = self.detector.detect(mp_image)
                
                if detection_result.detections:
                    # Sort by size descending
                    sorted_detections = sorted(
                        detection_result.detections, 
                        key=lambda d: d.bounding_box.width * d.bounding_box.height,
                        reverse=True
                    )
                    
                    # Track top 'count' faces
                    for i in range(min(count, len(sorted_detections))):
                        bbox = sorted_detections[i].bounding_box
                        x_center = bbox.origin_x + (bbox.width / 2)
                        face_x_histories[i].append(x_center)
                        if i == 0 and width > 0 and height > 0:
                            primary_face_area_ratios.append(
                                float((bbox.width * bbox.height) / float(width * height))
                            )
                next_sample_ms += 1000.0 / max(1, self.sample_rate_fps)
            
            frame_idx += 1
            
        cap.release()
        
        results = []
        detected_face_count = 0
        for i in range(count):
            history = face_x_histories[i]
            if history:
                detected_face_count += 1
                results.append(float(np.median(history)))
            else:
                # Pad with frame center fallback if fewer than 'count' faces were detected
                if i == 0:
                    logger.warning("[tracking] No subjects detected in %s. Falling back to center.", video_path.name)
                results.append(float(width / 2))
        
        primary_face_area_ratio = None
        if primary_face_area_ratios:
            primary_face_area_ratio = float(np.median(primary_face_area_ratios))

        return TrackingAnalysis(
            centers=results,
            detected_face_count=detected_face_count,
            primary_face_area_ratio=primary_face_area_ratio,
            frame_width=width,
            frame_height=height,
        )

    def get_optimal_centers(self, video_path: Path, count: int = 1) -> List[float]:
        """
        Analyzes the video and returns the recommended center X coordinates for the 'count' top faces.
        Returns exactly 'count' values, padded with frame_width/2 fallback if necessary.
        """
        return self.analyze_subjects(video_path, count=count).centers

def get_optimal_crop_x(video_path: Path) -> float:
    """Backward-compatible single-subject wrapper. Never raises IndexError."""
    tracker = SubjectTracker()
    centers = tracker.get_optimal_centers(video_path, count=1)
    return centers[0]  # safe: get_optimal_centers always returns exactly 'count' elements


def get_subject_tracker() -> SubjectTracker:
    return SubjectTracker()
