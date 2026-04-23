"""Initial Snapshot

Revision ID: 86f7cef2ee6c
Revises: 
Create Date: 2026-04-16 16:14:00.460638

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86f7cef2ee6c'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == 'postgresql'

    # 000 Enable UUID (Postgres only)
    if is_postgres:
        op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # 001 Users
    # Note: gen_random_uuid() is Postgres-specific. 
    # For SQLite, it will just be a default string or handled by the app.
    id_default = "(gen_random_uuid()::text)" if is_postgres else "NULL"
    timestamptz = "TIMESTAMPTZ" if is_postgres else "DATETIME"
    now = "NOW()" if is_postgres else "CURRENT_TIMESTAMP"

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id                  TEXT    PRIMARY KEY DEFAULT {id_default},
            email               TEXT    UNIQUE NOT NULL,
            full_name           TEXT,
            password_hash       TEXT,
            stripe_customer_id  TEXT    UNIQUE,
            created_at          {timestamptz} DEFAULT {now},
            updated_at          {timestamptz} DEFAULT {now}
        );
    """)

    # 002 Jobs
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS jobs (
            id                      TEXT        PRIMARY KEY DEFAULT {id_default},
            status                  TEXT        NOT NULL DEFAULT 'uploaded',
            source_video_url        TEXT        NOT NULL,
            audio_url               TEXT,
            transcript_json         TEXT,
            clips_json              TEXT,
            timeline_json           TEXT,
            failed_stage            TEXT,
            error_message           TEXT,
            retry_count             INTEGER     NOT NULL DEFAULT 0,
            prompt_version          TEXT        NOT NULL DEFAULT 'v4',
            estimated_cost_usd      REAL        NOT NULL DEFAULT 0,
            actual_cost_usd         REAL        NOT NULL DEFAULT 0,
            user_id                 TEXT,
            brand_kit_id            TEXT,
            campaign_id             TEXT,
            scheduled_publish_date  {timestamptz},
            created_at              {timestamptz} NOT NULL DEFAULT {now},
            updated_at              {timestamptz} NOT NULL DEFAULT {now}
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);")

    # 003 Brand Kits
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS brand_kits (
            id                TEXT       PRIMARY KEY DEFAULT {id_default},
            user_id           TEXT       NOT NULL,
            name              TEXT       NOT NULL DEFAULT 'Default Brand',
            font_name         TEXT       NOT NULL DEFAULT 'Arial',
            font_size         INTEGER    NOT NULL DEFAULT 22,
            bold              INTEGER    NOT NULL DEFAULT 1,
            alignment         INTEGER    NOT NULL DEFAULT 2,
            primary_colour    TEXT       NOT NULL DEFAULT '&H00FFFFFF',
            outline_colour    TEXT       NOT NULL DEFAULT '&H00000000',
            outline           INTEGER    NOT NULL DEFAULT 2,
            watermark_url     TEXT,
            intro_clip_url    TEXT,
            outro_clip_url    TEXT,
            is_default        INTEGER    NOT NULL DEFAULT 0,
            created_at        {timestamptz}  NOT NULL DEFAULT {now},
            updated_at        {timestamptz}  NOT NULL DEFAULT {now}
        );
    """)

    # 004 Campaigns
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS campaigns (
            id                TEXT       PRIMARY KEY DEFAULT {id_default},
            user_id           TEXT       NOT NULL,
            name              TEXT       NOT NULL,
            description       TEXT,
            schedule_config   TEXT       NOT NULL DEFAULT '{{"publish_interval_days": 1, "publish_hour": 9, "publish_timezone": "UTC"}}',
            status            TEXT       NOT NULL DEFAULT 'active',
            created_at        {timestamptz} NOT NULL DEFAULT {now},
            updated_at        {timestamptz} NOT NULL DEFAULT {now}
        );
    """)

    # 005 API Key / Watchdog tables
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS connected_sources (
            id               TEXT        PRIMARY KEY DEFAULT {id_default},
            user_id          TEXT        NOT NULL,
            name             TEXT        NOT NULL,
            source_type      TEXT        NOT NULL,
            config_json      TEXT        NOT NULL DEFAULT '{{}}',
            is_active        BOOLEAN     DEFAULT TRUE,
            last_polled_at   {timestamptz},
            last_error       TEXT,
            last_success_at  {timestamptz},
            created_at       {timestamptz} DEFAULT {now},
            updated_at       {timestamptz} DEFAULT {now}
        );
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS processed_videos (
            id               TEXT        PRIMARY KEY DEFAULT {id_default},
            source_id        TEXT        NOT NULL REFERENCES connected_sources(id) ON DELETE CASCADE,
            video_id         TEXT        NOT NULL,
            job_id           TEXT        REFERENCES jobs(id) ON DELETE SET NULL,
            created_at       {timestamptz} DEFAULT {now}
        );
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_source_video ON processed_videos(source_id, video_id);")

    # 006 Content DNA & Intelligence
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS user_score_weights (
            user_id          TEXT       PRIMARY KEY,
            weights          TEXT       DEFAULT '{{"hook_weight": 1.0, "emotion_weight": 1.0, "clarity_weight": 1.0, "story_weight": 1.0, "virality_weight": 1.0}}',
            manual_overrides TEXT       DEFAULT '[]',
            signal_count     INTEGER    DEFAULT 0,
            confidence_score REAL       DEFAULT 0.0,
            last_updated     {timestamptz} DEFAULT {now}
        );
    """)

    op.execute(f"""
        CREATE TABLE IF NOT EXISTS dna_learning_logs (
            id               TEXT        PRIMARY KEY DEFAULT {id_default},
            user_id          TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            log_type         TEXT        NOT NULL,
            dimension        TEXT,
            old_value        FLOAT,
            new_value        FLOAT,
            reasoning_code   TEXT        NOT NULL,
            sample_size      INT         DEFAULT 0,
            created_at       {timestamptz} DEFAULT {now}
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_dna_logs_user ON dna_learning_logs(user_id);")


def downgrade() -> None:
    # Safe downgrade: drop all tables (caution: destructive)
    op.execute("DROP TABLE IF EXISTS dna_learning_logs CASCADE;")
    op.execute("DROP TABLE IF EXISTS user_score_weights CASCADE;")
    op.execute("DROP TABLE IF EXISTS processed_videos CASCADE;")
    op.execute("DROP TABLE IF EXISTS connected_sources CASCADE;")
    op.execute("DROP TABLE IF EXISTS campaigns CASCADE;")
    op.execute("DROP TABLE IF EXISTS brand_kits CASCADE;")
    op.execute("DROP TABLE IF EXISTS jobs CASCADE;")
    op.execute("DROP TABLE IF EXISTS users CASCADE;")
