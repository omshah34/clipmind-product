"""Content DNA repository functions."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from db.connection import engine


def record_content_signal(
    user_id: UUID | str,
    job_id: UUID | str,
    clip_index: int,
    signal_type: str,
    metadata: dict | None = None,
) -> dict[str, Any]:
    """Record a user interaction signal for a clip."""
    query = text(
        """
        INSERT INTO content_signals (user_id, job_id, clip_index, signal_type, signal_metadata)
        VALUES (:user_id, :job_id, :clip_index, :signal_type, :metadata)
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "job_id": str(job_id),
                "clip_index": clip_index,
                "signal_type": signal_type,
                "metadata": json.dumps(metadata) if metadata else None,
            },
        ).one()
    return dict(row._mapping)
def get_user_signals(user_id: UUID | str, limit: int = 500) -> list[dict[str, Any]]:
    """Retrieve historical engagement signals for a user."""
    query = text(
        """
        SELECT * FROM content_signals
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "limit": limit}).all()
    
    results = []
    for row in rows:
        data = dict(row._mapping)
        if isinstance(data.get("signal_metadata"), str):
            try:
                data["signal_metadata"] = json.loads(data["signal_metadata"])
            except json.JSONDecodeError:
                data["signal_metadata"] = {}
        results.append(data)
    return results


def get_user_signal_counts(user_id: UUID | str) -> dict[str, int]:
    """Return per-signal counts for a user dashboard."""
    query = text(
        """
        SELECT signal_type, COUNT(*) AS count
        FROM content_signals
        WHERE user_id = :user_id
        GROUP BY signal_type
        """
    )
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id)}).all()

    counts = {str(row._mapping["signal_type"]): int(row._mapping["count"]) for row in rows}
    counts["total_signals"] = sum(counts.values())
    return counts


def get_user_score_weights(user_id: UUID | str) -> dict[str, Any] | None:
    """Retrieve score weights for a user."""
    query = text("SELECT * FROM user_score_weights WHERE user_id = :user_id")
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).one_or_none()
    
    if not row:
        return None
    
    data = dict(row._mapping)
    if isinstance(data.get("weights"), str):
        try:
            data["weights"] = json.loads(data["weights"])
        except json.JSONDecodeError:
            data["weights"] = {}
            
    if isinstance(data.get("manual_overrides"), str):
        try:
            data["manual_overrides"] = json.loads(data["manual_overrides"])
        except json.JSONDecodeError:
            data["manual_overrides"] = []
    else:
        data["manual_overrides"] = data.get("manual_overrides") or []
        
    return data


def update_user_score_weights(
    user_id: UUID | str,
    weights: dict,
    signal_count: int,
    confidence_score: float,
    manual_overrides: list[str] | None = None,
) -> dict[str, Any]:
    """Update or create score weights for a user."""
    query = text(
        """
        INSERT INTO user_score_weights (user_id, weights, signal_count, confidence_score, manual_overrides, last_updated)
        VALUES (:user_id, :weights, :signal_count, :confidence_score, :manual_overrides, CURRENT_TIMESTAMP)
        ON CONFLICT (user_id) DO UPDATE SET
            weights = EXCLUDED.weights,
            signal_count = EXCLUDED.signal_count,
            confidence_score = EXCLUDED.confidence_score,
            manual_overrides = COALESCE(EXCLUDED.manual_overrides, user_score_weights.manual_overrides),
            last_updated = EXCLUDED.last_updated
        RETURNING *
        """
    )
    with engine.begin() as connection:
        row = connection.execute(
            query,
            {
                "user_id": str(user_id),
                "weights": json.dumps(weights),
                "signal_count": signal_count,
                "confidence_score": confidence_score,
                "manual_overrides": json.dumps(manual_overrides) if manual_overrides is not None else None,
            },
        ).one()
    
    data = dict(row._mapping)
    if isinstance(data.get("weights"), str):
        data["weights"] = json.loads(data["weights"])
    if isinstance(data.get("manual_overrides"), str):
        data["manual_overrides"] = json.loads(data["manual_overrides"])
    return data


def log_dna_shift(
    user_id: str | UUID,
    log_type: str,
    reasoning_code: str,
    dimension: str | None = None,
    old_value: float | None = None,
    new_value: float | None = None,
    sample_size: int = 0,
) -> None:
    """Log a historical weight shift or milestone."""
    query = text("""
        INSERT INTO dna_learning_logs (
            user_id, log_type, dimension, old_value, new_value, reasoning_code, sample_size
        ) VALUES (
            :user_id, :log_type, :dimension, :old_val, :new_val, :code, :size
        )
    """)
    with engine.begin() as connection:
        connection.execute(query, {
            "user_id": str(user_id),
            "log_type": log_type,
            "dimension": dimension,
            "old_val": old_value,
            "new_val": new_value,
            "code": reasoning_code,
            "size": sample_size
        })


def get_dna_history(user_id: str | UUID, limit: int = 10) -> list[dict[str, Any]]:
    """Retrieve recent learning logs for DNA dashboard."""
    query = text("""
        SELECT * FROM dna_learning_logs
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT :limit
    """)
    with engine.connect() as connection:
        rows = connection.execute(query, {"user_id": str(user_id), "limit": limit}).all()
    return [dict(row._mapping) for row in rows]
def get_dna_logs_for_summary(user_id: str | UUID, hours: int = 24) -> list[dict[str, Any]]:
    """Retrieve learning logs from a specific window for synthesis."""
    query = text("""
        SELECT * FROM dna_learning_logs
        WHERE user_id = :user_id 
        AND created_at >= datetime('now', :hours_ago)
        ORDER BY created_at DESC
    """)
    # Note: SQLite and Postgres date math differs. Using SQLite syntax for local dev.
    # REFACTOR: Standardize via SQLAlchemy func or separate adapters if needed.
    with engine.connect() as connection:
        rows = connection.execute(query, {
            "user_id": str(user_id),
            "hours_ago": f"-{hours} hours"
        }).all()
    return [dict(row._mapping) for row in rows]


def save_executive_summary(user_id: str | UUID, summary_text: str, log_ids: list[str]) -> dict[str, Any]:
    """Persist an LLM-generated executive strategy summary."""
    query = text("""
        INSERT INTO dna_executive_summaries (user_id, summary_text, context_log_ids)
        VALUES (:u, :t, :ids)
        RETURNING *
    """)
    with engine.begin() as connection:
        row = connection.execute(query, {
            "u": str(user_id),
            "t": summary_text,
            "ids": json.dumps(log_ids)
        }).one()
    data = dict(row._mapping)
    return data


def get_latest_executive_summary(user_id: str | UUID) -> dict[str, Any] | None:
    """Retrieve the most recent executive summary for a user."""
    query = text("""
        SELECT * FROM dna_executive_summaries
        WHERE user_id = :user_id
        ORDER BY created_at DESC
        LIMIT 1
    """)
    with engine.connect() as connection:
        row = connection.execute(query, {"user_id": str(user_id)}).first()
    
    if not row:
        return None
        
    data = dict(row._mapping)
    if isinstance(data.get("context_log_ids"), str):
        try:
            data["context_log_ids"] = json.loads(data["context_log_ids"])
        except json.JSONDecodeError:
            data["context_log_ids"] = []
    return data
