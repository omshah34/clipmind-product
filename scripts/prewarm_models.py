"""File: scripts/prewarm_models.py
Purpose: Pre-load and cache AI models during Docker build.
"""
import mediapipe as mp
import numpy as np
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def prewarm():
    logger.info("Pre-warming MediaPipe models...")
    # Initialize Pose, Face, etc.
    try:
        mp_pose = mp.solutions.pose
        with mp_pose.Pose(static_image_mode=True, min_detection_confidence=0.5) as pose:
            # Run on a dummy blank image
            dummy_image = np.zeros((100, 100, 3), dtype=np.uint8)
            pose.process(dummy_image)
        logger.info("MediaPipe Pose model pre-warmed successfully.")
    except Exception as e:
        logger.warning(f"Could not pre-warm MediaPipe (non-critical in builds): {e}")

if __name__ == "__main__":
    prewarm()
