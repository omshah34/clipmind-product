"""Repository functions for relational clips storage."""

from __future__ import annotations

import json
import re
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


def normalize_tag(tag: str) -> str:
    """Canonical tag: lowercase, trimmed, alphanumeric + hyphens only."""
    tag = tag.strip().lower()
    tag = re.sub(r"[^a-z0-9\-]", "-", tag)
    tag = re.sub(r"-+", "-", tag).strip("-")
    return tag

def normalize_tags(tags: list[str]) -> list[str]:
    """Canonical tags: deduplicated and sorted."""
    seen, result = set(), []
    for tag in tags:
        normalized = normalize_tag(tag)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return sorted(result)  # Deterministic ordering

def upsert_clip_tags(clip_id: str, raw_tags: list[str]) -> None:
    """
    Gap 292: Apply normalized tags on every write.
    """
    clean = normalize_tags(raw_tags)
    query = text("UPDATE clips SET tags = :tags WHERE id = :clip_id")
    with engine.begin() as conn:
        conn.execute(query, {"tags": json.dumps(clean), "clip_id": clip_id})

def search_clips_fuzzy(query_str: str, user_id: str, similarity: float = 0.25) -> list[dict]:
    """
    Gap 295: Two-pass search:
    1. Exact full-text match (fast, ranked)
    2. Trigram fuzzy fallback if exact yields < 3 results
    """
    with engine.connect() as conn:
        # Pass 1: FTS (Postgres syntax)
        fts_query = text("""
            SELECT *, ts_rank(search_vector, plainto_tsquery('english', :q)) AS rank
            FROM clips
            WHERE user_id = :uid
              AND search_vector @@ plainto_tsquery('english', :q)
            ORDER BY rank DESC
            LIMIT 20
        """)
        fts_results = conn.execute(fts_query, {"q": query_str, "uid": str(user_id)}).fetchall()

        if len(fts_results) >= 3:
            return [dict(row._mapping) for row in fts_results]

        # Pass 2: Trigram fuzzy (Postgres similarity)
        fuzzy_query = text("""
            SELECT *, similarity(COALESCE(transcript_text, ''), :q) AS rank
            FROM clips
            WHERE user_id = :uid
              AND similarity(COALESCE(transcript_text, ''), :q) > :threshold
            ORDER BY rank DESC
            LIMIT 20
        """)
        fuzzy_results = conn.execute(fuzzy_query, {
            "q": query_str, 
            "uid": str(user_id), 
            "threshold": similarity
        }).fetchall()
        
        return [dict(row._mapping) for row in fuzzy_results]

def deduplicate_search_results(clips: list[dict], overlap_threshold: float = 0.7) -> list[dict]:
    """
    Gap 299: Remove clips that are temporal overlaps from the same source video.
    Keeps the highest-scoring clip when two clips share >70% of their time range.
    """
    if not clips:
        return []

    # Sort by score descending
    sorted_clips = sorted(clips, key=lambda c: float(c.get("virality_score", 0)), reverse=True)
    kept = []

    for candidate in sorted_clips:
        overlaps_kept = False
        source_id = candidate.get("source_video_id") or candidate.get("job_id")
        
        for kept_clip in kept:
            kept_source_id = kept_clip.get("source_video_id") or kept_clip.get("job_id")
            if kept_source_id != source_id:
                continue  # Different source — no overlap possible
                
            overlap = _temporal_overlap(
                float(candidate.get("start_time", 0)), float(candidate.get("end_time", 0)),
                float(kept_clip.get("start_time", 0)), float(kept_clip.get("end_time", 0)),
            )
            if overlap > overlap_threshold:
                overlaps_kept = True
                break  # Skip this candidate — lower score + overlaps

        if not overlaps_kept:
            kept.append(candidate)

    return kept

def _temporal_overlap(s1: float, e1: float, s2: float, e2: float) -> float:
    """Returns fraction of overlap relative to the shorter clip."""
    intersection = max(0, min(e1, e2) - max(s1, s2))
    shorter = min(e1 - s1, e2 - s2)
    return intersection / shorter if shorter > 0 else 0.0
