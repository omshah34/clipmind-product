from sqlalchemy import text
from db.connection import engine
import json

def get_test_job():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id FROM jobs WHERE status='completed' LIMIT 1")).fetchone()
        if result:
            return str(result[0])
        return None

if __name__ == "__main__":
    job_id = get_test_job()
    print(job_id)
