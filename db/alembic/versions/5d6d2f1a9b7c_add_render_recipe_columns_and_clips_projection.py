"""add render recipe columns and clips projection

Revision ID: 5d6d2f1a9b7c
Revises: 3a5b8c1d2e4f
Create Date: 2026-04-27 18:10:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5d6d2f1a9b7c"
down_revision: Union[str, None] = "3a5b8c1d2e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute(
            """
            ALTER TABLE render_jobs
            ADD COLUMN IF NOT EXISTS render_recipe_json TEXT,
            ADD COLUMN IF NOT EXISTS progress_percent INTEGER DEFAULT 0,
            ADD COLUMN IF NOT EXISTS error_message TEXT;
            """
        )

        op.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id           UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                clip_index       INTEGER NOT NULL,
                clip_url         TEXT NOT NULL,
                srt_url          TEXT,
                start_time       REAL NOT NULL,
                end_time         REAL NOT NULL,
                hook_score       REAL DEFAULT 0,
                emotion_score    REAL DEFAULT 0,
                clarity_score    REAL DEFAULT 0,
                story_score      REAL DEFAULT 0,
                virality_score   REAL DEFAULT 0,
                final_score      REAL DEFAULT 0,
                reason           TEXT,
                headlines        JSONB DEFAULT '[]'::jsonb,
                social_caption   TEXT,
                social_hashtags  JSONB DEFAULT '[]'::jsonb,
                layout_type      TEXT,
                visual_mode      TEXT,
                selected_hook    TEXT,
                render_recipe    JSONB DEFAULT '{}'::jsonb,
                created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clips_job_index ON clips (job_id, clip_index);")
        op.execute("CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips (job_id);")
        op.execute("ALTER TABLE clips ADD COLUMN IF NOT EXISTS srt_url TEXT;")
        op.execute("ALTER TABLE clips ADD COLUMN IF NOT EXISTS layout_type TEXT;")
        op.execute("ALTER TABLE clips ADD COLUMN IF NOT EXISTS visual_mode TEXT;")
        op.execute("ALTER TABLE clips ADD COLUMN IF NOT EXISTS selected_hook TEXT;")
        op.execute("ALTER TABLE clips ADD COLUMN IF NOT EXISTS render_recipe JSONB DEFAULT '{}'::jsonb;")
        return

    for statement in (
        "ALTER TABLE render_jobs ADD COLUMN render_recipe_json TEXT;",
        "ALTER TABLE render_jobs ADD COLUMN progress_percent INTEGER DEFAULT 0;",
        "ALTER TABLE render_jobs ADD COLUMN error_message TEXT;",
    ):
        try:
            op.execute(statement)
        except Exception:
            pass
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS clips (
            id               TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))),
            job_id           TEXT NOT NULL,
            clip_index       INTEGER NOT NULL,
            clip_url         TEXT NOT NULL,
            srt_url          TEXT,
            start_time       REAL NOT NULL,
            end_time         REAL NOT NULL,
            hook_score       REAL DEFAULT 0,
            emotion_score    REAL DEFAULT 0,
            clarity_score    REAL DEFAULT 0,
            story_score      REAL DEFAULT 0,
            virality_score   REAL DEFAULT 0,
            final_score      REAL DEFAULT 0,
            reason           TEXT,
            headlines        TEXT DEFAULT '[]',
            social_caption   TEXT,
            social_hashtags  TEXT DEFAULT '[]',
            layout_type      TEXT,
            visual_mode      TEXT,
            selected_hook    TEXT,
            render_recipe    TEXT DEFAULT '{}',
            created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clips_job_index ON clips (job_id, clip_index);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips (job_id);")
    for statement in (
        "ALTER TABLE clips ADD COLUMN srt_url TEXT;",
        "ALTER TABLE clips ADD COLUMN layout_type TEXT;",
        "ALTER TABLE clips ADD COLUMN visual_mode TEXT;",
        "ALTER TABLE clips ADD COLUMN selected_hook TEXT;",
        "ALTER TABLE clips ADD COLUMN render_recipe TEXT DEFAULT '{}';",
    ):
        try:
            op.execute(statement)
        except Exception:
            pass


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("ALTER TABLE render_jobs DROP COLUMN IF EXISTS error_message;")
        op.execute("ALTER TABLE render_jobs DROP COLUMN IF EXISTS progress_percent;")
        op.execute("ALTER TABLE render_jobs DROP COLUMN IF EXISTS render_recipe_json;")
        op.execute("DROP INDEX IF EXISTS idx_clips_job_id;")
        op.execute("DROP INDEX IF EXISTS idx_clips_job_index;")
        op.execute("DROP TABLE IF EXISTS clips;")
        return

    # SQLite downgrade is best-effort because DROP COLUMN is not universally available.
    op.execute("DROP INDEX IF EXISTS idx_clips_job_id;")
    op.execute("DROP INDEX IF EXISTS idx_clips_job_index;")
    op.execute("DROP TABLE IF EXISTS clips;")
