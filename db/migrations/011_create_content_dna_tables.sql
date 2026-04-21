-- migrations/011_create_content_dna_tables.sql

CREATE TABLE IF NOT EXISTS user_signals (
    signal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    job_id UUID,
    clip_index INTEGER,
    signal_type VARCHAR(50) NOT NULL, -- 'download', 'skip', 'edit', 'regenerate', 'publish', 'timeline_adjust'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_signals_user_id ON user_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_user_signals_job_id ON user_signals(job_id);

CREATE TABLE IF NOT EXISTS user_score_weights (
    user_id UUID PRIMARY KEY,
    hook_weight FLOAT DEFAULT 1.0,
    emotion_weight FLOAT DEFAULT 1.0,
    clarity_weight FLOAT DEFAULT 1.0,
    story_weight FLOAT DEFAULT 1.0,
    virality_weight FLOAT DEFAULT 1.0,
    confidence FLOAT DEFAULT 0.0,
    total_signals INTEGER DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
