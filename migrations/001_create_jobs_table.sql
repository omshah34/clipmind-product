CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS jobs (
    id                  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    status              VARCHAR(50)     NOT NULL DEFAULT 'uploaded',
    source_video_url    TEXT            NOT NULL,
    audio_url           TEXT,
    transcript_json     JSONB,
    clips_json          JSONB,
    failed_stage        VARCHAR(50),
    error_message       TEXT,
    retry_count         INTEGER         NOT NULL DEFAULT 0,
    prompt_version      VARCHAR(20)     NOT NULL DEFAULT 'v1',
    estimated_cost_usd  DECIMAL(10,6)   NOT NULL DEFAULT 0,
    actual_cost_usd     DECIMAL(10,6)   NOT NULL DEFAULT 0,
    created_at          TIMESTAMP       NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP       NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER jobs_updated_at
BEFORE UPDATE ON jobs
FOR EACH ROW EXECUTE FUNCTION update_updated_at();
