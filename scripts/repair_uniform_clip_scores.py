"""Repair legacy jobs whose clips were all stamped with the old uniform fallback score.

This script rescans stored clip spans using the local heuristic scorer so existing
jobs stop showing the old repeated 6.8 score pattern.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.caption_renderer import flatten_words
from services.clip_detector import calculate_final_score, estimate_heuristic_scores_for_range
from db.connection import engine
from db.repositories.jobs import get_job, update_job
from sqlalchemy import text


def _is_legacy_uniform_job(clips: list[dict]) -> bool:
    if len(clips) < 2:
        return False

    rounded_scores = {
        round(float(clip.get("final_score", 0.0) or 0.0), 1)
        for clip in clips
    }
    if len(rounded_scores) != 1:
        return False

    only_score = next(iter(rounded_scores))
    has_legacy_reason = all(
        "Fallback candidate beginning with" in str(clip.get("reason", ""))
        for clip in clips
    )
    missing_score_source = all(not clip.get("score_source") for clip in clips)
    return (abs(only_score - 6.8) <= 0.2 and missing_score_source) or has_legacy_reason


def repair_job(job_id: str) -> bool:
    job = get_job(job_id)
    if not job or not job.clips_json or not job.transcript_json:
        return False

    clips = [
        clip.model_dump() if hasattr(clip, "model_dump") else dict(clip)
        for clip in job.clips_json
    ]
    if not _is_legacy_uniform_job(clips):
        return False

    words = flatten_words(job.transcript_json)
    if not words:
        return False

    repaired: list[dict] = []
    for clip in clips:
        start_time = float(clip.get("start_time", 0.0))
        end_time = float(clip.get("end_time", 0.0))
        scores = estimate_heuristic_scores_for_range(
            words,
            start_time=start_time,
            end_time=end_time,
        )
        final_score = calculate_final_score(scores)
        repaired.append(
            {
                **clip,
                **scores,
                "final_score": final_score,
                "score_source": "heuristic",
                "score_confidence": 0.38,
                "reason": "Legacy fallback score repaired using transcript-aware heuristic estimation.",
            }
        )

    update_job(job_id, clips_json=repaired)
    return True


def main() -> None:
    query = text("SELECT id FROM jobs WHERE clips_json IS NOT NULL AND transcript_json IS NOT NULL")
    with engine.connect() as connection:
        job_ids = [str(row[0]) for row in connection.execute(query).fetchall()]

    repaired_count = 0
    for job_id in job_ids:
        if repair_job(job_id):
            repaired_count += 1
            print(f"repaired {job_id}")

    print(f"repaired_jobs={repaired_count}")


if __name__ == "__main__":
    main()
