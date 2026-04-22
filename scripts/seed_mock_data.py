import os
import json
import uuid
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# Load env to get DATABASE_URL (which we just set to sqlite)
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL.startswith("sqlite"):
    print(f"Error: DATABASE_URL is not SQLite: {DB_URL}")
    exit(1)

engine = create_engine(DB_URL)

# Mock Data
JOB_ID = "00000000-0000-0000-0000-000000000001"
USER_ID = "00000000-0000-0000-0000-000000000000"

TRANSCRIPT = [
    {"word": "Welcome", "start": 0.0, "end": 0.5},
    {"word": "to", "start": 0.5, "end": 0.7},
    {"word": "ClipMind,", "start": 0.7, "end": 1.2},
    {"word": "the", "start": 1.2, "end": 1.4},
    {"word": "future", "start": 1.4, "end": 1.8},
    {"word": "of", "start": 1.8, "end": 2.0},
    {"word": "video", "start": 2.0, "end": 2.4},
    {"word": "editing.", "start": 2.4, "end": 3.0},
    {"word": "This", "start": 3.0, "end": 3.3},
    {"word": "is", "start": 3.3, "end": 3.5},
    {"word": "a", "start": 3.5, "end": 3.6},
    {"word": "demo", "start": 3.6, "end": 4.0},
    {"word": "of", "start": 4.0, "end": 4.2},
    {"word": "smart", "start": 4.2, "end": 4.6},
    {"word": "transcript", "start": 4.6, "end": 5.2},
    {"word": "handles.", "start": 5.2, "end": 5.8},
    {"word": "You", "start": 5.8, "end": 6.1},
    {"word": "can", "start": 6.1, "end": 6.3},
    {"word": "now", "start": 6.3, "end": 6.6},
    {"word": "drag", "start": 6.6, "end": 7.0},
    {"word": "to", "start": 7.0, "end": 7.2},
    {"word": "select.", "start": 7.2, "end": 7.8},
]

CLIPS = [
    {
        "clip_id": "clip-1",
        "start_time": 0.0,
        "end_time": 3.0,
        "duration": 3.0,
        "final_score": 9.2,
        "reason": "Great introduction with clear hook.",
        "hook_score": 9.5,
        "emotion_score": 8.0,
        "clarity_score": 9.8,
        "story_score": 8.5,
        "virality_score": 9.0,
        "clip_url": "/api/v1/jobs/test-job-id-123/stream?start=0&end=3"
    },
    {
        "clip_id": "clip-2",
        "start_time": 4.0,
        "end_time": 7.8,
        "duration": 3.8,
        "final_score": 8.5,
        "reason": "Explanation of the new feature.",
        "hook_score": 7.0,
        "emotion_score": 7.5,
        "clarity_score": 9.5,
        "story_score": 9.0,
        "virality_score": 8.0,
        "clip_url": "/api/v1/jobs/test-job-id-123/stream?start=4&end=7.8"
    }
]

def seed():
    # 1. Initialize schema
    from db.init_sqlite import init_sqlite_tables
    init_sqlite_tables(engine)
    
    with engine.connect() as conn:
        # 2. Check if job exists
        res = conn.execute(text("SELECT id FROM jobs WHERE id = :id"), {"id": JOB_ID}).fetchone()
        if res:
            print(f"Job {JOB_ID} already exists. Skipping seed.")
            return

        # 3. Create User if not exists
        conn.execute(text("INSERT OR IGNORE INTO users (id, email) VALUES (:id, :email)"), 
                     {"id": USER_ID, "email": "dev@clipmind.ai"})
        
        # 4. Insert Job
        conn.execute(text("""
            INSERT INTO jobs (id, status, source_video_url, transcript_json, clips_json, user_id)
            VALUES (:id, :status, :url, :transcript, :clips, :user_id)
        """), {
            "id": JOB_ID,
            "status": "completed",
            "url": "https://example.com/video.mp4",
            "transcript": json.dumps(TRANSCRIPT),
            "clips": json.dumps(CLIPS),
            "user_id": USER_ID
        })
        conn.commit()
        print(f"Seeded job {JOB_ID} successfully.")

if __name__ == "__main__":
    seed()
