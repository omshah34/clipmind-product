from sqlalchemy import text, create_engine
import uuid

engine = create_engine("sqlite:///clipmind_dev.db")

def test():
    with engine.begin() as conn:
        res = conn.execute(text("""
            INSERT INTO jobs (status, source_video_url, prompt_version, estimated_cost_usd, user_id, language)
            VALUES ('uploaded', 'test_url_123', 'v2', 0.1, :uid, 'en')
            ON CONFLICT (user_id, source_video_url, prompt_version) WHERE user_id IS NOT NULL
            DO UPDATE SET updated_at = CURRENT_TIMESTAMP
            RETURNING *
        """), {"uid": str(uuid.uuid4())}).one_or_none()
        
        print("Keys:", res._mapping.keys())
        print("ID:", res.id)
        print("Row:", res)

if __name__ == "__main__":
    test()
