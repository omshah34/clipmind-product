-- Migration: v12_clips_table.sql
-- Purpose: Gap 210: Move clips from JSONB column to dedicated relational table for atomicity and integrity.

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
    headlines        JSONB DEFAULT '[]',
    social_caption   TEXT,
    social_hashtags  JSONB DEFAULT '[]',
    layout_type      TEXT,
    visual_mode      TEXT,
    selected_hook    TEXT,
    render_recipe    JSONB DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint to prevent duplicate indices per job
CREATE UNIQUE INDEX IF NOT EXISTS idx_clips_job_index ON clips (job_id, clip_index);
CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips (job_id);

-- Rollback Script:
-- DROP TABLE IF EXISTS clips;
