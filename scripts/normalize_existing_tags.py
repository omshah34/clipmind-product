import json
import logging
from sqlalchemy import text
from db.connection import engine
from db.repositories.clips import normalize_tags

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """
    Gap 292: Migration to clean existing data.
    """
    logger.info("Starting tag normalization migration...")
    
    with engine.connect() as conn:
        clips = conn.execute(text("SELECT id, tags FROM clips")).fetchall()
        
    updated_count = 0
    with engine.begin() as conn:
        for clip in clips:
            clip_id = clip._mapping["id"]
            raw_tags_json = clip._mapping["tags"]
            
            try:
                raw = json.loads(raw_tags_json or "[]")
                if not isinstance(raw, list):
                    raw = [str(raw)]
            except Exception:
                raw = []
                
            clean = normalize_tags(raw)
            clean_json = json.dumps(clean)
            
            if clean_json != raw_tags_json:
                conn.execute(
                    text("UPDATE clips SET tags = :tags WHERE id = :id"),
                    {"tags": clean_json, "id": clip_id}
                )
                updated_count += 1
    
    logger.info(f"Normalized tags for {len(clips)} clips. Updated {updated_count} records.")

if __name__ == "__main__":
    migrate()
