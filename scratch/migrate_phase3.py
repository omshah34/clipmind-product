"""File: scratch/migrate_phase3.py
Purpose: Database migration for Phase 3 Intelligence.
"""
import sys
import os
from sqlalchemy import text

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.connection import engine

def migrate():
    with engine.begin() as conn:
        print("Creating dna_learning_logs table...")
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dna_learning_logs (
                id               TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
                user_id          TEXT        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                log_type         TEXT        NOT NULL, -- 'weight_shift', 'milestone', 'advice'
                dimension        TEXT,
                old_value        FLOAT,
                new_value        FLOAT,
                reasoning_code   TEXT        NOT NULL, -- 'PUBLISH_RATE_SPIKE', 'CLEAN_SLATE', etc.
                sample_size      INT         DEFAULT 0,
                created_at       TIMESTAMPTZ DEFAULT NOW()
            );
        """))
        
        print("Creating indices for DNA logs...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_dna_logs_user ON dna_learning_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_dna_logs_created ON dna_learning_logs(created_at DESC);
        """))
        
    print("Migration complete.")

if __name__ == "__main__":
    migrate()
