"""File: db/init_db.py
Purpose: Create all tables using PostgreSQL-native DDL.
         Called once at startup from ``db.connection``.

         This is a full-fidelity translation of the 470-line init_sqlite.py
         preserving all 001-009 schema sections with PostgreSQL types.
"""

from __future__ import annotations

import logging
import os
import textwrap
from sqlalchemy import text
from core.config import settings

logger = logging.getLogger(__name__)

# fmt: off
_POSTGRES_SCHEMA = textwrap.dedent("""\
    -- Enable UUID extension
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- ====================================================================
    -- 009  users  (created first — many tables reference it)
    -- ====================================================================
    CREATE TABLE IF NOT EXISTS users (
        id                  TEXT    PRIMARY KEY DEFAULT (gen_random_uuid()::text),
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
        id               TEXT PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        job_id           TEXT NOT NULL,
        previous_status   TEXT,
        new_status        TEXT NOT NULL,
        stage            TEXT,
        payload_json     TEXT NOT NULL DEFAULT '{}',
        source           TEXT NOT NULL DEFAULT 'system',
        request_id       TEXT,
        user_id          TEXT,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_job_state_events_job_id ON job_state_events(job_id);
    CREATE INDEX IF NOT EXISTS idx_job_state_events_created_at ON job_state_events(created_at DESC);

    -- ====================================================================
    -- 001  jobs
    -- ====================================================================
    CREATE TABLE IF NOT EXISTS jobs (
        id                      TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
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
        scheduled_publish_date  TIMESTAMPTZ,
        language                TEXT        DEFAULT 'en',
        is_rejected             BOOLEAN     NOT NULL DEFAULT FALSE,
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

    -- ====================================================================
    -- 002  brand_kits
    -- ====================================================================
    CREATE TABLE IF NOT EXISTS brand_kits (
        id                TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
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
        created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
        updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_brand_kits_user_id ON brand_kits(user_id);

    -- ====================================================================
    -- 004  campaigns
    -- ====================================================================
    CREATE TABLE IF NOT EXISTS campaigns (
        id                TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id           TEXT       NOT NULL,
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
        id                 TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id            TEXT       NOT NULL,
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
        id               TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id          TEXT       NOT NULL,
        url              TEXT       NOT NULL,
        event_types      TEXT       NOT NULL,
        is_active        INTEGER    NOT NULL DEFAULT 1,
        secret           TEXT       NOT NULL,
        retry_count      INTEGER    NOT NULL DEFAULT 0,
        retry_max        INTEGER    NOT NULL DEFAULT 5,
        timeout_seconds  INTEGER    NOT NULL DEFAULT 30,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_webhooks_user_id ON webhooks(user_id);

    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        id               TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        webhook_id       TEXT       NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
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
        id                 TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id            TEXT       NOT NULL,
        integration_type   TEXT       NOT NULL,
        name               TEXT       NOT NULL,
        config             TEXT       NOT NULL,
        is_active          INTEGER    NOT NULL DEFAULT 1,
        last_triggered_at  TIMESTAMPTZ,
        trigger_events     TEXT       NOT NULL,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_integrations_user_id ON integrations(user_id);

    -- ====================================================================
    -- 006  clip_performance / performance_alerts / platform_credentials
    -- ====================================================================
    CREATE TABLE IF NOT EXISTS clip_performance (
        id                          TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id                     TEXT       NOT NULL,
        job_id                      TEXT       NOT NULL,
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
        id              TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id         TEXT       NOT NULL,
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
        user_id         TEXT       NOT NULL,
        alert_type      TEXT       NOT NULL,
        last_alerted_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (user_id, alert_type)
    );

    CREATE TABLE IF NOT EXISTS platform_credentials (
        id                       TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id                  TEXT       NOT NULL,
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
        id              TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id         TEXT       NOT NULL,
        job_id          TEXT       NOT NULL,
        clip_index      INTEGER    NOT NULL,
        signal_type     TEXT       NOT NULL,
        signal_metadata TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_content_signals_user ON content_signals(user_id);
    CREATE INDEX IF NOT EXISTS idx_content_signals_job ON content_signals(job_id);

    CREATE TABLE IF NOT EXISTS user_score_weights (
        user_id          TEXT       PRIMARY KEY,
        weights          TEXT       DEFAULT '{"hook_weight": 1.0, "emotion_weight": 1.0, "clarity_weight": 1.0, "story_weight": 1.0, "virality_weight": 1.0}',
        manual_overrides TEXT       DEFAULT '[]', -- List of weight keys that are locked
        signal_count     INTEGER    DEFAULT 0,
        confidence_score REAL       DEFAULT 0.0,
        last_updated     TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS clip_sequences (
        id                      TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id                 TEXT       NOT NULL,
        job_id                  TEXT       NOT NULL,
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

    CREATE TABLE IF NOT EXISTS render_jobs (
        id              TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        job_id          TEXT       NOT NULL,
        clip_index      INTEGER    NOT NULL,
        edited_srt      TEXT,
        edited_style    TEXT,
        status          TEXT       DEFAULT 'queued',
        output_url      TEXT,
        created_at      TIMESTAMPTZ DEFAULT NOW(),
        completed_at    TIMESTAMPTZ
    );

    CREATE INDEX IF NOT EXISTS idx_render_jobs_status ON render_jobs(status);

    CREATE TABLE IF NOT EXISTS social_accounts (
        id                       TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id                  TEXT       NOT NULL,
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
        id                TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id           TEXT       NOT NULL,
        job_id            TEXT       NOT NULL,
        clip_index        INTEGER    NOT NULL,
        platform          TEXT       NOT NULL,
        social_account_id TEXT,
        platform_clip_id  TEXT,
        platform_url      TEXT,
        caption           TEXT,
        hashtags          TEXT,
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
        id           TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        owner_id     TEXT       NOT NULL,
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
        id            TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        workspace_id  TEXT       NOT NULL,
        user_id       TEXT       NOT NULL,
        role          TEXT       NOT NULL,
        joined_at     TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (workspace_id, user_id)
    );

    CREATE INDEX IF NOT EXISTS idx_workspace_members_workspace ON workspace_members(workspace_id);
    CREATE INDEX IF NOT EXISTS idx_workspace_members_user ON workspace_members(user_id);

    CREATE TABLE IF NOT EXISTS workspace_clients (
        id                   TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        workspace_id         TEXT       NOT NULL,
        client_name          TEXT       NOT NULL,
        client_contact_email TEXT,
        description          TEXT,
        is_active            INTEGER    DEFAULT 1,
        created_at           TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_workspace_clients_workspace ON workspace_clients(workspace_id);

    CREATE TABLE IF NOT EXISTS client_portals (
        id            TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        workspace_id  TEXT       NOT NULL,
        client_id     TEXT       NOT NULL,
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
        id                   TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        portal_id            TEXT       NOT NULL,
        job_id               TEXT       NOT NULL,
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
        id             TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        workspace_id   TEXT       NOT NULL,
        user_id        TEXT,
        action         TEXT       NOT NULL,
        resource_type  TEXT,
        resource_id    TEXT,
        details        TEXT,
        created_at     TIMESTAMPTZ DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_workspace_audit_logs_workspace ON workspace_audit_logs(workspace_id);

    CREATE TABLE IF NOT EXISTS workspace_metrics (
        id                TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        workspace_id      TEXT       NOT NULL,
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
        user_id               TEXT       PRIMARY KEY,
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
        id                      TEXT       PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id                 TEXT       NOT NULL,
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
        id               TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id          TEXT        NOT NULL,
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
        id               TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        source_id        TEXT        NOT NULL REFERENCES connected_sources(id) ON DELETE CASCADE,
        video_id         TEXT        NOT NULL,
        job_id           TEXT        REFERENCES jobs(id) ON DELETE SET NULL,
        created_at       TIMESTAMPTZ DEFAULT NOW()
    );

    -- Unique constraint for O(1) deduplication and race-condition safety
    CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_source_video ON processed_videos(source_id, video_id);

    CREATE TABLE IF NOT EXISTS publish_queue (
        id               TEXT        PRIMARY KEY DEFAULT (gen_random_uuid()::text),
        user_id          TEXT        NOT NULL,
        job_id           TEXT        NOT NULL,
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
""")
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
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ["development", "local"]:
            logger.info("ENVIRONMENT=%s detected — seeding mock user and workspace...", env)
            
            # 1. UPSERT Mock User
            conn.execute(text("""
                INSERT INTO users (id, email, full_name, created_at, updated_at)
                VALUES (
                    :user_id, 
                    'local@clipmind.com', 
                    'Local Dev User', 
                    NOW(), NOW()
                )
                ON CONFLICT (id) DO NOTHING;
            """), {"user_id": settings.dev_mock_user_id})
            
            # 2. UPSERT Default Workspace
            conn.execute(text("""
                INSERT INTO workspaces (id, owner_id, name, slug, is_active, created_at, updated_at)
                VALUES (
                    :user_id, 
                    :user_id, 
                    'Local Dev Workspace', 
                    'local-dev', 
                    1, NOW(), NOW()
                )
                ON CONFLICT (id) DO NOTHING;
            """), {"user_id": settings.dev_mock_user_id})
            
            # 3. UPSERT Workspace Membership
            conn.execute(text("""
                INSERT INTO workspace_members (id, workspace_id, user_id, role, joined_at)
                VALUES (
                    :user_id, 
                    :user_id, 
                    :user_id, 
                    'owner', 
                    NOW()
                )
                ON CONFLICT (id) DO NOTHING;
            """), {"user_id": settings.dev_mock_user_id})

            logger.info("Mock user and workspace seeded successfully.")

    try:
        from db.feature_flags import get_feature_flag

        get_feature_flag.cache_clear()
    except Exception:
        logger.debug("Feature flag cache clear skipped during PostgreSQL init", exc_info=True)

    logger.info("PostgreSQL tables initialized successfully.")
