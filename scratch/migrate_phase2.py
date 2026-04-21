"""File: migrations/010_watchdog_schema.py
Purpose: Database migration for Phase 2 Autopilot.
"""
import sys
import os
from sqlalchemy import text

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import engine

def migrate():
    with engine.begin() as conn:
        print("Migrating connected_sources...")
        conn.execute(text("ALTER TABLE connected_sources ADD COLUMN IF NOT EXISTS last_error TEXT;"))
        conn.execute(text("ALTER TABLE connected_sources ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;"))
        
        print("Creating processed_videos table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS processed_videos (
                id               TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
                source_id        TEXT        NOT NULL REFERENCES connected_sources(id) ON DELETE CASCADE,
                video_id         TEXT        NOT NULL,
                job_id           TEXT        REFERENCES jobs(id) ON DELETE SET NULL,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        
        print("Creating deduplication index...")
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_source_video ON processed_videos(source_id, video_id);
        """))
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
