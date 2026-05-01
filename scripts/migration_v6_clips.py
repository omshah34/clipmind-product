import json
import logging
import os
import sys

# Add project root to sys.path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import redis
    from sqlalchemy import text, create_engine
    from core.config import settings
except ImportError:
    print("Missing dependencies. Ensure sqlalchemy and redis are installed.")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("migration_v6")

def run_migration():
    if not settings.database_url:
        logger.error("DATABASE_URL not configured.")
        return

    logger.info(f"Connecting to database: {settings.database_url.split('@')[-1]}")
    engine = create_engine(settings.database_url)
    
    redis_client = None
    try:
        redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
    except Exception as e:
        logger.warning(f"Redis unavailable ({e}). Resumption tracking disabled, but DB unique constraints still ensure idempotency.")
    
    # Track migrated jobs to avoid redundant JSON parsing in the same run
    REDIS_SET_KEY = "migration_v6_processed_jobs"
    
    logger.info("Starting Phase 6 Data Migration...")
    
    with engine.begin() as conn:
        # 1. Audit status strings - find any that don't match the new CHECK constraint
        valid_statuses = {'uploaded', 'processing', 'completed', 'failed', 'rejected'}
        rows = conn.execute(text("SELECT id, status FROM jobs")).fetchall()
        
        dirty_jobs = [row for row in rows if row.status not in valid_statuses]
        if dirty_jobs:
            logger.info(f"Found {len(dirty_jobs)} jobs with invalid status. Cleaning up...")
            for job in dirty_jobs:
                # Map old/legacy statuses to new valid ones
                old_status = job.status.lower() if job.status else ""
                if "fail" in old_status or "err" in old_status:
                    new_status = 'failed'
                elif "reject" in old_status:
                    new_status = 'rejected'
                elif "done" in old_status or "finish" in old_status:
                    new_status = 'completed'
                elif "proc" in old_status:
                    new_status = 'processing'
                else:
                    new_status = 'uploaded'
                
                conn.execute(
                    text("UPDATE jobs SET status = :status WHERE id = :id"),
                    {"status": new_status, "id": job.id}
                )
            logger.info("Status cleanup complete.")

        # 2. Migrate clips from JSONB column to clips table
        jobs_to_migrate = conn.execute(text(
            "SELECT id, clips_json FROM jobs WHERE clips_json IS NOT NULL"
        )).fetchall()
        
        total = len(jobs_to_migrate)
        migrated_jobs_count = 0
        migrated_clips_count = 0
        
        for i, job in enumerate(jobs_to_migrate):
            job_id = str(job.id)
            
            # Redis check for resumption optimization
            if redis_client and redis_client.sismember(REDIS_SET_KEY, job_id):
                continue
                
            clips_data = job.clips_json
            if not clips_data:
                continue
                
            # Handle if it's a string instead of dict/list
            if isinstance(clips_data, str):
                try:
                    clips_data = json.loads(clips_data)
                except:
                    logger.warning(f"Failed to parse clips_json for job {job_id}")
                    continue
            
            if not isinstance(clips_data, list):
                logger.warning(f"clips_json for job {job_id} is not a list; skipping.")
                continue

            for clip in clips_data:
                try:
                    # Map Pydantic field names to DB column names
                    # model: hook_headlines -> db: headlines
                    # model: social_hashtags (list) -> db: social_hashtags (jsonb)
                    
                    headlines = clip.get("hook_headlines", [])
                    if not isinstance(headlines, list):
                        headlines = []
                        
                    hashtags = clip.get("social_hashtags", [])
                    if not isinstance(hashtags, list):
                        hashtags = []

                    # Use CURRENT_TIMESTAMP instead of NOW() for SQLite/Postgres compatibility
                    # Use INSERT OR IGNORE for SQLite, ON CONFLICT DO NOTHING for Postgres
                    
                    sql = """
                        INSERT INTO clips (
                            job_id, clip_index, clip_url, srt_url, start_time, end_time,
                            hook_score, emotion_score, clarity_score, story_score, virality_score,
                            final_score, reason, headlines, social_caption, social_hashtags,
                            layout_type, visual_mode, selected_hook, render_recipe, created_at
                        ) VALUES (
                            :job_id, :clip_index, :clip_url, :srt_url, :start_time, :end_time,
                            :hook_score, :emotion_score, :clarity_score, :story_score, :virality_score,
                            :final_score, :reason, :headlines, :social_caption, :social_hashtags,
                            :layout_type, :visual_mode, :selected_hook, :render_recipe, CURRENT_TIMESTAMP
                        )
                    """
                    
                    if engine.dialect.name == "sqlite":
                        sql = sql.replace("INSERT INTO", "INSERT OR IGNORE INTO")
                    else:
                        sql += " ON CONFLICT (job_id, clip_index) DO NOTHING"

                    conn.execute(text(sql), {
                        "job_id": job.id,
                        "clip_index": clip.get("clip_index", 0),
                        "clip_url": clip.get("clip_url", ""),
                        "srt_url": clip.get("srt_url"),
                        "start_time": clip.get("start_time", 0.0),
                        "end_time": clip.get("end_time", 0.0),
                        "hook_score": clip.get("hook_score", 0.0),
                        "emotion_score": clip.get("emotion_score", 0.0),
                        "clarity_score": clip.get("clarity_score", 0.0),
                        "story_score": clip.get("story_score", 0.0),
                        "virality_score": clip.get("virality_score", 0.0),
                        "final_score": clip.get("final_score", 0.0),
                        "reason": clip.get("reason", ""),
                        "headlines": json.dumps(headlines),
                        "social_caption": clip.get("social_caption"),
                        "social_hashtags": json.dumps(hashtags),
                        "layout_type": clip.get("layout_type"),
                        "visual_mode": clip.get("visual_mode"),
                        "selected_hook": clip.get("selected_hook"),
                        "render_recipe": json.dumps(clip.get("render_recipe", {})),
                    })
                    migrated_clips_count += 1
                except Exception as e:
                    logger.error(f"Error migrating clip {clip.get('clip_index')} for job {job_id}: {e}")
            
            if redis_client:
                redis_client.sadd(REDIS_SET_KEY, job_id)
            migrated_jobs_count += 1
            
            if migrated_jobs_count % 100 == 0:
                logger.info(f"Progress: {i+1}/{total} jobs processed...")

    logger.info(f"Migration complete.")
    logger.info(f" - Jobs processed: {migrated_jobs_count}")
    logger.info(f" - Clips migrated: {migrated_clips_count}")
    
    if redis_client:
        redis_client.delete(REDIS_SET_KEY)
        logger.info("Cleared Redis resumption tracker.")

if __name__ == "__main__":
    run_migration()
