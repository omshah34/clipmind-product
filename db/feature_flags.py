"""Feature flag helpers backed by env vars with optional DB overrides."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from sqlalchemy import text

from db.connection import engine
from core.config import settings


def _env_flag_name(flag_name: str) -> str:
    normalized = flag_name.upper().replace("-", "_").replace(".", "_")
    return f"{settings.feature_flag_prefix}{normalized}"


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on", "enabled"}:
        return True
    if normalized in {"0", "false", "no", "off", "disabled"}:
        return False
    return None


@lru_cache(maxsize=256)
def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    env_value = _parse_bool(os.getenv(_env_flag_name(flag_name)))
    if env_value is not None:
        return env_value

    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT enabled
                    FROM feature_flags
                    WHERE flag_name = :flag_name
                    LIMIT 1
                    """
                ),
                {"flag_name": flag_name},
            ).one_or_none()
            if row is None:
                return default
            return bool(row._mapping["enabled"])
    except Exception:
        return default


def set_feature_flag(flag_name: str, enabled: bool, metadata: dict[str, Any] | None = None) -> None:
    payload = json.dumps(metadata or {}, default=str)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO feature_flags (flag_name, enabled, metadata_json)
                VALUES (:flag_name, :enabled, :metadata_json)
                ON CONFLICT(flag_name) DO UPDATE SET
                    enabled = excluded.enabled,
                    metadata_json = excluded.metadata_json,
                    updated_at = CURRENT_TIMESTAMP
                """
            ),
            {
                "flag_name": flag_name,
                "enabled": 1 if enabled else 0,
                "metadata_json": payload,
            },
        )
    get_feature_flag.cache_clear()


def feature_flag_enabled(flag_name: str, default: bool = False) -> bool:
    return get_feature_flag(flag_name, default=default)
