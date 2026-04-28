"""Quick sanity check: create_job no longer returns id=None."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, create_engine

engine = create_engine("sqlite:///clipmind_dev.db")

import uuid

# Simulate exactly what create_job now does
new_id = str(uuid.uuid4())
params = {
    "id": new_id,
    "status": "uploaded",
    "source_video_url": f"test_fix_verify_{new_id[:8]}",
    "prompt_version": "v2",
    "estimated_cost_usd": 0.1,
    "user_id": str(uuid.uuid4()),
    "brand_kit_id": None,
    "campaign_id": None,
    "language": "en",
}

with engine.begin() as conn:
    row = conn.execute(
        text("""
            INSERT INTO jobs (id, status, source_video_url, prompt_version, estimated_cost_usd, user_id, brand_kit_id, campaign_id, language)
            VALUES (:id, :status, :source_video_url, :prompt_version, :estimated_cost_usd, :user_id, :brand_kit_id, :campaign_id, :language)
            ON CONFLICT (user_id, source_video_url, prompt_version) WHERE user_id IS NOT NULL
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """),
        params
    ).one_or_none()

if row is None:
    print("FAIL: row is None")
elif row.id is None:
    print(f"FAIL: id is None — schema still broken. Row: {row}")
else:
    print(f"OK: id={row.id}, status={row.status}")
