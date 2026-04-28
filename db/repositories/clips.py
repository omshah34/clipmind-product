"""Repository functions for relational clips storage."""

from __future__ import annotations

import json
from uuid import UUID
from typing import Any

from sqlalchemy import text
from db.connection import engine

def insert_clip_rows(conn, job_id: str, clips: list[dict]):
    """Insert multiple clip rows using an existing connection/transaction."""
    if not clips:
        return

    # Prepare values for bulk insert
    columns = [
        "job_id", "clip_index", "clip_url", "srt_url", "start_time", "end_time",
        "hook_score", "emotion_score", "clarity_score", "story_score", "virality_score",
        "final_score", "reason", "headlines", "social_caption", "social_hashtags", "layout_type",
        "visual_mode", "selected_hook", "render_recipe"
    ]
    
    query = text(f"""
        INSERT INTO clips ({", ".join(columns)})
        VALUES (
            :job_id, :clip_index, :clip_url, :srt_url, :start_time, :end_time,
            :hook_score, :emotion_score, :clarity_score, :story_score, :virality_score,
            :final_score, :reason, :headlines, :social_caption, :social_hashtags, :layout_type,
            :visual_mode, :selected_hook, :render_recipe
        )
        ON CONFLICT (job_id, clip_index) DO UPDATE SET
            clip_url = EXCLUDED.clip_url,
            srt_url = EXCLUDED.srt_url,
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            final_score = EXCLUDED.final_score,
            reason = EXCLUDED.reason,
            headlines = EXCLUDED.headlines,
            social_caption = EXCLUDED.social_caption,
            social_hashtags = EXCLUDED.social_hashtags,
            layout_type = EXCLUDED.layout_type,
            visual_mode = EXCLUDED.visual_mode,
            selected_hook = EXCLUDED.selected_hook,
            render_recipe = EXCLUDED.render_recipe
    """)

    for clip in clips:
        params = {
            "job_id": job_id,
            "clip_index": clip.get("clip_index"),
            "clip_url": clip.get("clip_url"),
            "srt_url": clip.get("srt_url"),
            "start_time": float(clip.get("start_time", 0)),
            "end_time": float(clip.get("end_time", 0)),
            "hook_score": float(clip.get("hook_score", 0)),
            "emotion_score": float(clip.get("emotion_score", 0)),
            "clarity_score": float(clip.get("clarity_score", 0)),
            "story_score": float(clip.get("story_score", 0)),
            "virality_score": float(clip.get("virality_score", 0)),
            "final_score": float(clip.get("final_score", 0)),
            "reason": clip.get("reason"),
            "headlines": json.dumps(clip.get("hook_headlines", [])),
            "social_caption": clip.get("social_caption"),
            "social_hashtags": json.dumps(clip.get("social_hashtags", [])),
            "layout_type": clip.get("layout_suggestion") or clip.get("layout_type"),
            "visual_mode": clip.get("visual_mode"),
            "selected_hook": clip.get("selected_hook"),
            "render_recipe": json.dumps(clip.get("render_recipe", {})),
        }
        conn.execute(query, params)

def get_job_clips(job_id: str) -> list[dict]:
    """Retrieve all clips for a specific job from the relational table."""
    query = text("SELECT * FROM clips WHERE job_id = :job_id ORDER BY clip_index ASC")
    with engine.connect() as conn:
        rows = conn.execute(query, {"job_id": job_id}).all()
    
    results = []
    for row in rows:
        data = dict(row._mapping)
        # Parse JSON fields
        for field in ["headlines", "social_hashtags", "render_recipe"]:
            if isinstance(data.get(field), str):
                try:
                    data[field] = json.loads(data[field])
                except json.JSONDecodeError:
                    data[field] = [] if field != "render_recipe" else {}
        results.append(data)
    return results
