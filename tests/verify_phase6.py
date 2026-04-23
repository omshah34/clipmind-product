"""File: tests/verify_phase6.py
Purpose: Manual and automated verification of Phase 6 Intelligence features.
         Tests: Manual Weight Overrides, Alert Cooldowns, and Omni-channel Aggregation.
"""

import sys
import os
import json
from uuid import uuid4
from datetime import datetime, timezone, timedelta

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.repositories.content_dna import update_user_score_weights, get_user_score_weights
from db.repositories.performance import create_performance_alert, list_performance_alerts as get_performance_alerts, upsert_clip_performance
from db.repositories.users import get_user_performance_summary
from db.repositories.jobs import create_job
from db.connection import engine
from services.content_dna import apply_performance_feedback

def test_manual_overrides():
    print("\n--- Testing Manual Overrides ---")
    user_id = str(uuid4())
    
    # 1. Setup dummy job with clip data so DNA engine finds it
    job = create_job(
        user_id=user_id,
        source_video_url="http://test.com",
        prompt_version="v4",
        estimated_cost_usd=0.01
    )
    job_id = str(job.id)
    
    # Manually update clips_json in DB (easier than full pipeline)
    from sqlalchemy import text
    with engine.begin() as conn:
        clips = [
            {
                "clip_index": 0, 
                "hook_score": 9.0, 
                "emotion_score": 9.0, 
                "clarity_score": 5.0, 
                "story_score": 5.0, 
                "virality_score": 5.0,
                "start_time": 0.0,
                "end_time": 30.0,
                "duration": 30.0,
                "clip_url": "http://clip.com/0.mp4",
                "final_score": 8.5,
                "reason": "Viral potential"
            }
        ]
        # Table name is 'jobs'
        conn.execute(text("UPDATE jobs SET clips_json = :clips WHERE id = :job_id"), {
            "clips": json.dumps(clips),
            "job_id": job_id
        })
        
    # 2. Setup minimum sample size (n=5) so gating passes
    for i in range(5):
        upsert_clip_performance(
            user_id=user_id, job_id=str(uuid4()), clip_index=i,
            platform="youtube", source_type="mock", views=100, likes=10,
            engagement_score=0.1, performance_delta=0, milestone_tier=None,
            window_complete=True
        )

    # 3. Initialize weights with 'hook_weight' locked
    initial_weights = {"hook_weight": 1.0, "emotion_weight": 1.0, "clarity_weight": 1.0, "story_weight": 1.0, "virality_weight": 1.0}
    overrides = ["hook_weight"]
    
    update_user_score_weights(user_id, initial_weights, 10, 0.5, overrides)
    
    # 4. Apply feedback that SHOULD shift hook_weight up
    apply_performance_feedback(
        user_id=user_id,
        job_id=job_id,
        clip_index=0,
        delta=0.8,         # Strong positive
        milestone_tier="viral"
    )
    
    updated_dna = get_user_score_weights(user_id)
    weights = updated_dna["weights"]
    
    print(f"Hook Weight (Locked): {weights.get('hook_weight')} (Expected: 1.0)")
    print(f"Emotion Weight (Unlocked): {weights.get('emotion_weight')} (Expected: > 1.0)")
    
    assert weights.get("hook_weight") == 1.0, "Locked weight was modified!"
    assert weights.get("emotion_weight") > 1.0, "Unlocked weight was not modified!"
    print("OK: Manual Overrides respected.")

def test_alert_cooldown():
    print("\n--- Testing Alert Cooldown (24h) ---")
    user_id = str(uuid4())
    alert_type = "weight_shift"
    
    # 1. Create first alert
    a1 = create_performance_alert(user_id, alert_type, "First Alert")
    print(f"First alert created: {a1 is not None}")
    
    # 2. Create second alert (same type) immediately
    a2 = create_performance_alert(user_id, alert_type, "Second Alert (Should fail cooldown)")
    print(f"Second alert created: {a2 is not None} (Expected: False)")
    
    alerts = get_performance_alerts(user_id, unread_only=False)
    print(f"Total alerts in DB: {len(alerts)} (Expected: 1)")
    
    assert a1 is not None and len(a1) > 0
    assert a2 == {}  # Empty dict = cooldown suppressed
    assert len(alerts) == 1
    print("OK: Alert cooldown functioning correctly.")

def test_omni_channel_aggregation():
    print("\n--- Testing Omni-channel Aggregation ---")
    user_id = str(uuid4())
    job_id = str(uuid4())
    clip_index = 5
    
    # 1. Insert performance for YouTube
    upsert_clip_performance(
        user_id=user_id, job_id=job_id, clip_index=clip_index,
        platform="youtube", source_type="mock", views=1000, likes=100,
        engagement_score=0.1, performance_delta=0, milestone_tier=None,
        window_complete=True
    )
    
    # 2. Insert performance for TikTok (Same clip)
    upsert_clip_performance(
        user_id=user_id, job_id=job_id, clip_index=clip_index,
        platform="tiktok", source_type="mock", views=500, likes=50,
        engagement_score=0.1, performance_delta=0, milestone_tier=None,
        window_complete=True
    )
    
    # 3. Get summary
    summary = get_user_performance_summary(user_id)
    # 2 platform rows (youtube + tiktok), 1500 TOTAL views
    print(f"Total Clips: {summary['total_clips']} (Expected: 2)")
    print(f"Total Views: {summary['total_views']} (Expected: 1500)")
    
    assert summary["total_clips"] == 2
    assert summary["total_views"] == 1500
    print("OK: Omni-channel Aggregation logic verified.")

if __name__ == "__main__":
    try:
        test_manual_overrides()
        test_alert_cooldown()
        test_omni_channel_aggregation()
        print("\nSUMMARY: PHASE 6 VERIFICATION SUCCESSFUL")
    except Exception as e:
        print(f"\n[X] VERIFICATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
