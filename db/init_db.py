"""File: db/init_db.py
Purpose: Create all tables using PostgreSQL-native DDL.
         Called once at startup from ``db.connection``.

         This is a full-fidelity translation of the 470-line init_sqlite.py
         preserving all 001-009 schema sections with PostgreSQL types.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from sqlalchemy import text
from core.config import settings

logger = logging.getLogger(__name__)

# Schema is loaded from a .sql file so the IDE type-checker never sees raw SQL
# in this Python module (avoids Pyrefly virtual-file parse errors).
_POSTGRES_SCHEMA: str = (
    Path(__file__).parent.joinpath("postgres_schema.sql").read_text(encoding="utf-8")
)



# fmt: off
# ─── Seed SQL constants ──────────────────────────────────────────────────────
# Stored as named constants (not inline strings) so the IDE type-checker
# does not extract them as virtual Python files to analyse.
_SQL_SEED_USER = (
    "INSERT INTO users"
    " (id, email, full_name, mock_credit_balance, created_at, updated_at)"
    " VALUES (:user_id::UUID, 'local@clipmind.com', 'Local Dev User',"
    " 100.0, NOW(), NOW())"
    " ON CONFLICT (id) DO NOTHING"
)

_SQL_SEED_WORKSPACE = (
    "INSERT INTO workspaces"
    " (id, owner_id, name, slug, is_active, created_at, updated_at)"
    " VALUES (:user_id::UUID, :user_id::UUID, 'Local Dev Workspace',"
    " 'local-dev', 1, NOW(), NOW())"
    " ON CONFLICT (id) DO NOTHING"
)

_SQL_SEED_MEMBER = (
    "INSERT INTO workspace_members (id, workspace_id, user_id, role, joined_at)"
    " VALUES (:user_id::UUID, :user_id::UUID, :user_id::UUID, 'owner', NOW())"
    " ON CONFLICT (id) DO NOTHING"
)
# fmt: on

def init_db_tables(engine) -> None:
    """Execute all CREATE TABLE IF NOT EXISTS statements.
    Automatically detects if we are using PostgreSQL or SQLite.
    """
    if engine.dialect.name == "sqlite":
        from db.init_sqlite import init_sqlite_tables
        init_sqlite_tables(engine)
        return

    logger.info("Initializing PostgreSQL tables...")
    with engine.begin() as conn:
        conn.execute(text(_POSTGRES_SCHEMA))

        # ─── Mock Data Seeding (Local Dev Only) ──────────────────────────────────
        env = (settings.environment or "production").lower()
        if env in ["development", "local"]:
            logger.info("ENVIRONMENT=%s detected — seeding mock user and workspace...", env)

            # 1. UPSERT Mock User (Idempotent)
            conn.execute(text(_SQL_SEED_USER), {"user_id": settings.dev_mock_user_id})

            # 2. UPSERT Default Workspace (Idempotent)
            conn.execute(text(_SQL_SEED_WORKSPACE), {"user_id": settings.dev_mock_user_id})

            # 3. UPSERT Workspace Membership (Idempotent)
            conn.execute(text(_SQL_SEED_MEMBER), {"user_id": settings.dev_mock_user_id})

            logger.info("Mock user and workspace seeded successfully.")

    try:
        from db.feature_flags import get_feature_flag

        get_feature_flag.cache_clear()
    except Exception:
        logger.debug("Feature flag cache clear skipped during PostgreSQL init", exc_info=True)

    logger.info("PostgreSQL tables initialized successfully.")
