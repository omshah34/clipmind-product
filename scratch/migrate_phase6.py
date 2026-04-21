import sqlalchemy
from sqlalchemy import text

engine = sqlalchemy.create_engine('postgresql://clipmind:your_secure_password@localhost:5432/clipmind')

with engine.begin() as conn:
    print("Running migration for Phase 6...")
    conn.execute(text("ALTER TABLE user_score_weights ADD COLUMN IF NOT EXISTS manual_overrides TEXT DEFAULT '[]';"))
    conn.execute(text("ALTER TABLE performance_alerts ADD COLUMN IF NOT EXISTS metadata_json TEXT;"))
    
    # Safely convert is_read to boolean if it's still an integer
    res = conn.execute(text("SELECT data_type FROM information_schema.columns WHERE table_name = 'performance_alerts' AND column_name = 'is_read'")).scalar()
    if res == 'integer':
        print("Converting is_read from integer to boolean...")
        conn.execute(text("ALTER TABLE performance_alerts ALTER COLUMN is_read DROP DEFAULT;"))
        conn.execute(text("ALTER TABLE performance_alerts ALTER COLUMN is_read TYPE BOOLEAN USING (CASE WHEN is_read=1 THEN TRUE ELSE FALSE END);"))
        conn.execute(text("ALTER TABLE performance_alerts ALTER COLUMN is_read SET DEFAULT FALSE;"))
    else:
        print(f"is_read already type: {res}")
    
    # Make clip_perf_id nullable (it might have been created as NOT NULL in a previous step)
    conn.execute(text("ALTER TABLE performance_alerts ALTER COLUMN clip_perf_id DROP NOT NULL;"))
    
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS alert_cooldowns (
            user_id TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            last_alerted_at TIMESTAMPTZ DEFAULT NOW(),
            PRIMARY KEY (user_id, alert_type)
        );
    """))
    print("Migration successful.")
