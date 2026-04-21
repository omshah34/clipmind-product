-- migrations/012_create_feature_flags_job_state_events_and_platform_url.sql

CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name       TEXT PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 0,
    metadata_json   JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_state_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID NOT NULL,
    previous_status  TEXT,
    new_status       TEXT NOT NULL,
    stage            TEXT,
    payload_json     JSONB NOT NULL DEFAULT '{}'::jsonb,
    source           TEXT NOT NULL DEFAULT 'system',
    request_id       TEXT,
    user_id          TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_state_events_job_id ON job_state_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_state_events_created_at ON job_state_events(created_at DESC);

ALTER TABLE published_clips
    ADD COLUMN IF NOT EXISTS platform_url TEXT;
