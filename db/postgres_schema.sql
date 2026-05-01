-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ====================================================================
-- 009  users  (created first — many tables reference it)
-- ====================================================================
CREATE TABLE IF NOT EXISTS users (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT    UNIQUE NOT NULL,
    full_name           TEXT,
    password_hash       TEXT,
    stripe_customer_id  TEXT    UNIQUE,
    mock_credit_balance REAL    DEFAULT 0,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ====================================================================
-- feature_flags / job_state_events
-- ====================================================================
CREATE TABLE IF NOT EXISTS feature_flags (
    flag_name       TEXT PRIMARY KEY,
    enabled         BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json   TEXT NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS job_state_events (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID NOT NULL,
    previous_status   TEXT,
    new_status        TEXT NOT NULL,
    stage            TEXT,
    payload_json     TEXT NOT NULL DEFAULT '{}',
    source           TEXT NOT NULL DEFAULT 'system',
    request_id       TEXT,
    user_id          UUID,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_job_state_events_job_id ON job_state_events(job_id);
CREATE INDEX IF NOT EXISTS idx_job_state_events_created_at ON job_state_events(created_at DESC);

-- ====================================================================
-- 001  jobs
-- ====================================================================
CREATE TABLE IF NOT EXISTS jobs (
    id                      UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    status                  TEXT        NOT NULL DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'completed', 'failed', 'rejected')),
    source_video_url        TEXT        NOT NULL,
    proxy_video_url         TEXT,
    audio_url               TEXT,
    transcript_json         JSONB,
    clips_json              JSONB,
    timeline_json           JSONB,
    failed_stage            TEXT,
    error_message           TEXT,
    retry_count             INTEGER     NOT NULL DEFAULT 0,
    prompt_version          TEXT        NOT NULL DEFAULT 'v4',
    estimated_cost_usd      REAL        NOT NULL DEFAULT 0,
    actual_cost_usd         REAL        NOT NULL DEFAULT 0,
    user_id                 UUID,
    brand_kit_id            UUID,
    campaign_id             UUID,
    scheduled_publish_date  TIMESTAMPTZ,
    language                TEXT        DEFAULT 'en',
    is_rejected             BOOLEAN     NOT NULL DEFAULT FALSE,
    token_prompt_total      INTEGER     DEFAULT 0,
    token_completion_total  INTEGER     DEFAULT 0,
    rejected_at             TIMESTAMPTZ,
    completed_at            TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_user_id ON jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_jobs_brand_kit_id ON jobs(brand_kit_id);
CREATE INDEX IF NOT EXISTS idx_jobs_campaign_id ON jobs(campaign_id);

-- Gap 33: Unique constraints for job deduplication
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe_user ON jobs (user_id, source_video_url, prompt_version) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe_anon ON jobs (source_video_url, prompt_version) WHERE user_id IS NULL;

-- ====================================================================
-- 002  brand_kits
-- ====================================================================
CREATE TABLE IF NOT EXISTS brand_kits (
    id                UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID       NOT NULL,
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
    vocabulary_hints  TEXT[],    -- Gap 72: Custom words for Whisper
    is_default        INTEGER    NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brand_kits_user_id ON brand_kits(user_id);

-- ====================================================================
-- 004  campaigns
-- ====================================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id                UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID       NOT NULL,
    name              TEXT       NOT NULL,
    description       TEXT,
    schedule_config   TEXT       NOT NULL DEFAULT '{"publish_interval_days": 1, "publish_hour": 9, "publish_timezone": "UTC"}',
    status            TEXT       NOT NULL DEFAULT 'active',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campaigns_user_id ON campaigns(user_id);
CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status);

-- ====================================================================
-- 005  api_keys / webhooks / webhook_deliveries / integrations
-- ====================================================================
CREATE TABLE IF NOT EXISTS api_keys (
    id                 UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID       NOT NULL,
    name               TEXT       NOT NULL,
    key_prefix         TEXT       NOT NULL,
    key_hash           TEXT       NOT NULL,
    is_active          INTEGER    NOT NULL DEFAULT 1,
    last_used_at       TIMESTAMPTZ,
    rate_limit_per_min INTEGER    NOT NULL DEFAULT 60,
    scopes             TEXT       DEFAULT 'clips:read,jobs:read',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at         TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys(user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_prefix ON api_keys(key_prefix);

CREATE TABLE IF NOT EXISTS webhooks (
    id               UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID       NOT NULL,
    url              TEXT       NOT NULL,
    event_types      TEXT       NOT NULL,
    is_active        INTEGER    NOT NULL DEFAULT 1,
    secret           TEXT       NOT NULL,
    retry_count      INTEGER    NOT NULL DEFAULT 0,
    retry_max        INTEGER    NOT NULL DEFAULT 5,
    timeout_seconds  INTEGER    NOT NULL DEFAULT 30,
    deleted_at       TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_webhooks_user_id ON webhooks(user_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_active_by_user ON webhooks(user_id, created_at DESC) WHERE deleted_at IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='webhooks' AND column_name='deleted_at') THEN
        ALTER TABLE webhooks ADD COLUMN deleted_at TIMESTAMPTZ;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id               UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id       UUID       NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type       TEXT       NOT NULL,
    event_data       TEXT       NOT NULL,
    http_status      INTEGER,
    response_body    TEXT,
    attempt_count    INTEGER    NOT NULL DEFAULT 1,
    next_retry_at    TIMESTAMPTZ,
    status           TEXT       NOT NULL DEFAULT 'pending',
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id ON webhook_deliveries(webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_status ON webhook_deliveries(status);

CREATE TABLE IF NOT EXISTS integrations (
    id                 UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID       NOT NULL,
    integration_type   TEXT       NOT NULL,
    name               TEXT       NOT NULL,
    config             TEXT       NOT NULL,
    is_active          INTEGER    NOT NULL DEFAULT 1,
    deleted_at         TIMESTAMPTZ,
    last_triggered_at  TIMESTAMPTZ,
    trigger_events     TEXT       NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_integrations_user_id ON integrations(user_id);
CREATE INDEX IF NOT EXISTS idx_integrations_active_by_user ON integrations(user_id, created_at DESC) WHERE deleted_at IS NULL;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='integrations' AND column_name='deleted_at') THEN
        ALTER TABLE integrations ADD COLUMN deleted_at TIMESTAMPTZ;
    END IF;
END $$;

-- ====================================================================
-- 006  clip_performance / performance_alerts / platform_credentials
-- ====================================================================
CREATE TABLE IF NOT EXISTS clip_performance (
    id                          UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     UUID       NOT NULL,
    job_id                      UUID       NOT NULL,
    clip_index                  INTEGER    NOT NULL,
    platform                    TEXT       NOT NULL,
    platform_clip_id            TEXT,
    source_type                 TEXT       DEFAULT 'real', -- 'mock', 'real'
    ai_predicted_score          REAL,
    performance_delta           REAL       DEFAULT 0.0,
    milestone_tier              TEXT,      -- 'emerging', 'validated', 'viral'
    window_complete             BOOLEAN    DEFAULT FALSE,
    views                       INTEGER    DEFAULT 0,
    likes                       INTEGER    DEFAULT 0,
    saves                       INTEGER    DEFAULT 0,
    shares                      INTEGER    DEFAULT 0,
    comments                    INTEGER    DEFAULT 0,
    engagement_score            REAL       DEFAULT 0.0,
    save_rate                   REAL       DEFAULT 0.0,
    share_rate                  REAL       DEFAULT 0.0,
    comment_rate                REAL       DEFAULT 0.0,
    average_watch_time_seconds  REAL,
    completion_rate             REAL,
    published_date              TIMESTAMPTZ,
    synced_at                   TIMESTAMPTZ DEFAULT NOW(),
    created_at                  TIMESTAMPTZ DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clip_perf_user_id ON clip_performance(user_id);
CREATE INDEX IF NOT EXISTS idx_clip_perf_job_id ON clip_performance(job_id);
CREATE INDEX IF NOT EXISTS idx_clip_perf_lookup ON clip_performance(user_id, job_id, clip_index);

-- Idempotent column additions for Phase 5
DO $$ 
BEGIN 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_performance' AND column_name='source_type') THEN
        ALTER TABLE clip_performance ADD COLUMN source_type TEXT DEFAULT 'real';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_performance' AND column_name='ai_predicted_score') THEN
        ALTER TABLE clip_performance ADD COLUMN ai_predicted_score REAL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_performance' AND column_name='performance_delta') THEN
        ALTER TABLE clip_performance ADD COLUMN performance_delta REAL DEFAULT 0.0;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_performance' AND column_name='milestone_tier') THEN
        ALTER TABLE clip_performance ADD COLUMN milestone_tier TEXT;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='clip_performance' AND column_name='window_complete') THEN
        ALTER TABLE clip_performance ADD COLUMN window_complete BOOLEAN DEFAULT FALSE;
    END IF;
    
    -- Constraint
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'unique_clip_perf') THEN
        ALTER TABLE clip_performance ADD CONSTRAINT unique_clip_perf UNIQUE (user_id, job_id, clip_index, platform);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS performance_alerts (
    id              UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID       NOT NULL,
    alert_type      TEXT       NOT NULL, -- 'milestone', 'weight_shift', 'sync_error'
    message         TEXT       NOT NULL,
    is_read         BOOLEAN    DEFAULT FALSE,
    metadata_json   TEXT,      -- stores {clip_perf_id, delta, threshold, weight_key, etc}
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_perf_alerts_user_id ON performance_alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_perf_alerts_type ON performance_alerts(alert_type);

-- 24-hour Cooldown Tracker
CREATE TABLE IF NOT EXISTS alert_cooldowns (
    user_id         UUID       NOT NULL,
    alert_type      TEXT       NOT NULL,
    last_alerted_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, alert_type)
);

CREATE TABLE IF NOT EXISTS performance_sync_jobs (
    job_id         TEXT       PRIMARY KEY,
    user_id        UUID       NOT NULL,
    status         TEXT       NOT NULL,
    error_message  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_sync_jobs_user_id ON performance_sync_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_performance_sync_jobs_status ON performance_sync_jobs(status);

CREATE TABLE IF NOT EXISTS platform_credentials (
    id                       UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID       NOT NULL,
    platform                 TEXT       NOT NULL,
    access_token_encrypted   TEXT,
    refresh_token_encrypted  TEXT,
    expires_at               TIMESTAMPTZ,
    account_id               TEXT,
    account_name             TEXT,
    scopes                   TEXT,
    synced_at                TIMESTAMPTZ,
    is_active                BOOLEAN    NOT NULL DEFAULT TRUE,
    last_error               TEXT,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, platform)
);

-- ====================================================================
-- 007  content_signals / user_score_weights / clip_sequences /
--      render_jobs / social_accounts / published_clips
-- ====================================================================
    -- Phase 7: platform_credentials health
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='platform_credentials' AND column_name='is_active') THEN
            ALTER TABLE platform_credentials ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='platform_credentials' AND column_name='last_error') THEN
            ALTER TABLE platform_credentials ADD COLUMN last_error TEXT;
        END IF;
    END $$;
CREATE TABLE IF NOT EXISTS content_signals (
    id              UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID       NOT NULL,
    job_id          UUID       NOT NULL,
    clip_index      INTEGER    NOT NULL,
    signal_type     TEXT       NOT NULL,
    signal_metadata TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_content_signals_user ON content_signals(user_id);
CREATE INDEX IF NOT EXISTS idx_content_signals_job ON content_signals(job_id);

CREATE TABLE IF NOT EXISTS user_score_weights (
    user_id          UUID       PRIMARY KEY,
    weights          TEXT       DEFAULT '{"hook_weight": 1.0, "emotion_weight": 1.0, "clarity_weight": 1.0, "story_weight": 1.0, "virality_weight": 1.0}',
    manual_overrides TEXT       DEFAULT '[]', -- List of weight keys that are locked
    signal_count     INTEGER    DEFAULT 0,
    confidence_score REAL       DEFAULT 0.0,
    last_updated     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dna_learning_logs (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    log_type         TEXT        NOT NULL, -- 'shift', 'milestone', 'manual_reset'
    dimension        TEXT,
    old_value        REAL,
    new_value        REAL,
    reasoning_code   TEXT,
    sample_size      INTEGER     DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dna_learning_logs_user ON dna_learning_logs(user_id);

CREATE TABLE IF NOT EXISTS dna_executive_summaries (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    summary_text     TEXT        NOT NULL,
    context_log_ids  TEXT        NOT NULL, -- JSON list of log IDs used
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dna_executive_summaries_user ON dna_executive_summaries(user_id);

CREATE TABLE IF NOT EXISTS clip_sequences (
    id                      UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID       NOT NULL,
    job_id                  UUID       NOT NULL,
    sequence_title          TEXT,
    clip_indices            TEXT       NOT NULL,
    series_description      TEXT,
    suggested_captions      TEXT       NOT NULL,
    cliffhanger_scores      TEXT       NOT NULL,
    platform_optimizations  TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_clip_sequences_user ON clip_sequences(user_id);

CREATE TABLE IF NOT EXISTS clips (
    id               UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id           UUID       NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    clip_index       INTEGER    NOT NULL,
    clip_url         TEXT       NOT NULL,
    srt_url          TEXT,
    start_time       REAL       NOT NULL,
    end_time         REAL       NOT NULL,
    hook_score       REAL       DEFAULT 0,
    emotion_score    REAL       DEFAULT 0,
    clarity_score    REAL       DEFAULT 0,
    story_score      REAL       DEFAULT 0,
    virality_score   REAL       DEFAULT 0,
    final_score      REAL       DEFAULT 0,
    reason           TEXT,
    headlines        JSONB      DEFAULT '[]'::jsonb,
    social_caption   TEXT,
    social_hashtags  JSONB      DEFAULT '[]'::jsonb,
    layout_type      TEXT,
    visual_mode      TEXT,
    selected_hook    TEXT,
    render_recipe    JSONB      DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clips_job_index ON clips (job_id, clip_index);
CREATE INDEX IF NOT EXISTS idx_clips_job_id ON clips (job_id);

CREATE TABLE IF NOT EXISTS render_jobs (
    id              UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID       NOT NULL,
    job_id          UUID       NOT NULL,
    clip_index      INTEGER    NOT NULL,
    edited_srt      TEXT,
    edited_style    TEXT,
    render_recipe_json TEXT,
    status          TEXT       DEFAULT 'queued',
    progress_percent INTEGER   DEFAULT 0,
    output_url      TEXT,
    error_message   TEXT,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status);
CREATE INDEX IF NOT EXISTS idx_render_jobs_user ON render_jobs(user_id);

CREATE TABLE IF NOT EXISTS social_accounts (
    id                       UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                  UUID       NOT NULL,
    platform                 TEXT       NOT NULL,
    account_id               TEXT       NOT NULL,
    account_username         TEXT,
    access_token_encrypted   TEXT,
    refresh_token_encrypted  TEXT,
    token_expires_at         TIMESTAMPTZ,
    is_connected             INTEGER    DEFAULT 1,
    last_sync                TIMESTAMPTZ,
    created_at               TIMESTAMPTZ DEFAULT NOW(),
    updated_at               TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, platform, account_id)
);

CREATE INDEX IF NOT EXISTS idx_social_accounts_user ON social_accounts(user_id);

CREATE TABLE IF NOT EXISTS published_clips (
    id                UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID       NOT NULL,
    job_id            UUID       NOT NULL,
    clip_index        INTEGER    NOT NULL,
    platform          TEXT       NOT NULL,
    social_account_id UUID,
    platform_clip_id  TEXT,
    platform_url      TEXT,
    caption           TEXT,
    hashtags          TEXT,
    asset_path       TEXT,
    published_at      TIMESTAMPTZ,
    scheduled_at      TIMESTAMPTZ,
    status            TEXT       DEFAULT 'draft',
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_published_clips_user ON published_clips(user_id);
CREATE INDEX IF NOT EXISTS idx_published_clips_platform ON published_clips(platform);

-- ====================================================================
-- 008  workspaces / member / client / portals / audit / metrics
-- ====================================================================
CREATE TABLE IF NOT EXISTS workspaces (
    id           UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id     UUID       NOT NULL,
    name         TEXT       NOT NULL,
    slug         TEXT       UNIQUE NOT NULL,
    plan         TEXT       DEFAULT 'starter',
    settings     TEXT       DEFAULT '{}',
    logo_url     TEXT,
    brand_color  TEXT,
    is_active    INTEGER    DEFAULT 1,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_slug ON workspaces(slug);

CREATE TABLE IF NOT EXISTS workspace_members (
    id            UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID       NOT NULL,
    user_id       UUID       NOT NULL,
    role          TEXT       NOT NULL,
    joined_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

CREATE TABLE IF NOT EXISTS workspace_clients (
    id                   UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id         UUID       NOT NULL,
    client_name          TEXT       NOT NULL,
    client_contact_email TEXT,
    description          TEXT,
    is_active            INTEGER    DEFAULT 1,
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_clients_workspace ON workspace_clients(workspace_id);

CREATE TABLE IF NOT EXISTS client_portals (
    id            UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  UUID       NOT NULL,
    client_id     UUID       NOT NULL,
    portal_slug   TEXT       UNIQUE NOT NULL,
    branding      TEXT       DEFAULT '{}',
    is_active     INTEGER    DEFAULT 1,
    token_secret  TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_client_portals_workspace ON client_portals(workspace_id);
CREATE INDEX IF NOT EXISTS idx_client_portals_slug ON client_portals(portal_slug);

CREATE TABLE IF NOT EXISTS portal_submissions (
    id                   UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    portal_id            UUID       NOT NULL,
    job_id               UUID       NOT NULL,
    submission_token     TEXT       UNIQUE NOT NULL,
    status               TEXT       DEFAULT 'pending',
    client_feedback      TEXT,
    approved_clip_indices TEXT,
    expires_at           TIMESTAMPTZ,
    created_at           TIMESTAMPTZ DEFAULT NOW(),
    updated_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_portal_submissions_status ON portal_submissions(status);

CREATE TABLE IF NOT EXISTS workspace_audit_logs (
    id             UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id   UUID       NOT NULL,
    user_id        UUID,
    action         TEXT       NOT NULL,
    resource_type  TEXT,
    resource_id    UUID,
    details        TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_workspace ON workspace_audit_logs(workspace_id);

CREATE TABLE IF NOT EXISTS workspace_metrics (
    id                UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id      UUID       NOT NULL,
    period_start      DATE       NOT NULL,
    period_end        DATE       NOT NULL,
    videos_processed  INTEGER    DEFAULT 0,
    clips_generated   INTEGER    DEFAULT 0,
    clips_published   INTEGER    DEFAULT 0,
    api_calls         INTEGER    DEFAULT 0,
    storage_gb        REAL       DEFAULT 0.0,
    estimated_cost    REAL       DEFAULT 0.0,
    created_at        TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (workspace_id, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_workspace_metrics_workspace ON workspace_metrics(workspace_id);

-- ====================================================================
-- user_preferences
-- ====================================================================
CREATE TABLE IF NOT EXISTS user_preferences (
    user_id               UUID       PRIMARY KEY,
    goals                 TEXT       DEFAULT '[]',
    target_platform       TEXT,
    preferences_json      TEXT       DEFAULT '{}',
    onboarding_completed  BOOLEAN    DEFAULT FALSE,
    created_at            TIMESTAMPTZ DEFAULT NOW(),
    updated_at            TIMESTAMPTZ DEFAULT NOW()
);

-- ====================================================================
-- 009  subscriptions
-- ====================================================================
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID       NOT NULL,
    stripe_subscription_id  TEXT       UNIQUE NOT NULL,
    stripe_price_id         TEXT       NOT NULL,
    status                  TEXT       NOT NULL,
    current_period_end      TIMESTAMPTZ,
    cancel_at_period_end    INTEGER    DEFAULT 0,
    plan_tier               TEXT       NOT NULL DEFAULT 'free',
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);

-- ====================================================================
-- 010  Autopilot (Connected Sources & Publish Queue)
-- ====================================================================
CREATE TABLE IF NOT EXISTS connected_sources (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    name             TEXT        NOT NULL,
    source_type      TEXT        NOT NULL, -- 'youtube_channel', 'rss_feed', 'manual_batch'
    config_json      TEXT        NOT NULL DEFAULT '{}',
    is_active        BOOLEAN     DEFAULT TRUE,
    last_polled_at   TIMESTAMPTZ,
    last_error       TEXT,
    last_success_at  TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_connected_sources_user ON connected_sources(user_id);

-- ====================================================================
-- 011  Processed Video Deduplication (Watchdog)
-- ====================================================================
CREATE TABLE IF NOT EXISTS processed_videos (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id        UUID        NOT NULL REFERENCES connected_sources(id) ON DELETE CASCADE,
    video_id         TEXT        NOT NULL,
    job_id           UUID        REFERENCES jobs(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- Unique constraint for O(1) deduplication and race-condition safety
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_source_video ON processed_videos(source_id, video_id);

CREATE TABLE IF NOT EXISTS publish_queue (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID        NOT NULL,
    job_id           UUID        NOT NULL,
    clip_index       INTEGER     NOT NULL,
    platform         TEXT        NOT NULL,
    scheduled_for    TIMESTAMPTZ NOT NULL,
    status           TEXT        DEFAULT 'pending', -- 'pending', 'processing', 'published', 'failed'
    platform_url     TEXT,
    error_message    TEXT,
    published_at     TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_publish_queue_status ON publish_queue(status);
CREATE INDEX IF NOT EXISTS idx_publish_queue_scheduled ON publish_queue(scheduled_for);

-- ====================================================================
-- Gap 237: Content-Addressable Storage (CAS) asset registry
-- Maps a SHA-256 hex digest to a canonical storage URL so that the
-- same source video uploaded by multiple users is stored only once.
-- ====================================================================
CREATE TABLE IF NOT EXISTS cas_assets (
    sha256          TEXT        PRIMARY KEY,
    canonical_url   TEXT        NOT NULL,
    size_bytes      BIGINT      NOT NULL DEFAULT 0,
    ref_count       INTEGER     NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cas_assets_last_seen ON cas_assets(last_seen_at DESC);

-- ====================================================================
-- Gap 28: Foreign Key Constraints & Cascades
-- ====================================================================
DO $$ 
BEGIN 
    -- jobs constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_user_id') THEN
        ALTER TABLE jobs ADD CONSTRAINT fk_jobs_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_brand_kit_id') THEN
        ALTER TABLE jobs ADD CONSTRAINT fk_jobs_brand_kit_id FOREIGN KEY (brand_kit_id) REFERENCES brand_kits(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_campaign_id') THEN
        ALTER TABLE jobs ADD CONSTRAINT fk_jobs_campaign_id FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE SET NULL;
    END IF;

    -- brand_kits constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_brand_kits_user_id') THEN
        ALTER TABLE brand_kits ADD CONSTRAINT fk_brand_kits_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- campaigns constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_campaigns_user_id') THEN
        ALTER TABLE campaigns ADD CONSTRAINT fk_campaigns_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- api_keys constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_api_keys_user_id') THEN
        ALTER TABLE api_keys ADD CONSTRAINT fk_api_keys_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- webhooks constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_webhooks_user_id') THEN
        ALTER TABLE webhooks ADD CONSTRAINT fk_webhooks_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- integrations constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_integrations_user_id') THEN
        ALTER TABLE integrations ADD CONSTRAINT fk_integrations_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- clip_performance constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clip_perf_user_id') THEN
        ALTER TABLE clip_performance ADD CONSTRAINT fk_clip_perf_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clip_perf_job_id') THEN
        ALTER TABLE clip_performance ADD CONSTRAINT fk_clip_perf_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;
    END IF;

    -- performance_alerts constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_perf_alerts_user_id') THEN
        ALTER TABLE performance_alerts ADD CONSTRAINT fk_perf_alerts_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- alert_cooldowns constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_alert_cooldowns_user_id') THEN
        ALTER TABLE alert_cooldowns ADD CONSTRAINT fk_alert_cooldowns_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- platform_credentials constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_platform_creds_user_id') THEN
        ALTER TABLE platform_credentials ADD CONSTRAINT fk_platform_creds_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- clip_sequences constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clip_sequences_user_id') THEN
        ALTER TABLE clip_sequences ADD CONSTRAINT fk_clip_sequences_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_clip_sequences_job_id') THEN
        ALTER TABLE clip_sequences ADD CONSTRAINT fk_clip_sequences_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;
    END IF;

    -- job_state_events constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_job_state_events_job_id') THEN
        ALTER TABLE job_state_events ADD CONSTRAINT fk_job_state_events_job_id FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_job_state_events_user_id') THEN
        ALTER TABLE job_state_events ADD CONSTRAINT fk_job_state_events_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- workspaces constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_workspaces_owner_id') THEN
        ALTER TABLE workspaces ADD CONSTRAINT fk_workspaces_owner_id FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

    -- workspace_members constraints
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_workspace_members_workspace_id') THEN
        ALTER TABLE workspace_members ADD CONSTRAINT fk_workspace_members_workspace_id FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_workspace_members_user_id') THEN
        ALTER TABLE workspace_members ADD CONSTRAINT fk_workspace_members_user_id FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
    END IF;

END $$;
