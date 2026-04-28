"""Reset stuck jobs that are in a non-terminal state but have no active worker."""
from sqlalchemy import text, create_engine

engine = create_engine("sqlite:///clipmind_dev.db")

with engine.begin() as conn:
    result = conn.execute(text("""
        UPDATE jobs
        SET status = 'failed',
            error_message = 'Worker crashed (EncodeError: generator not JSON serializable). Fixed and ready to retry.',
            failed_stage = 'pipeline_start'
        WHERE status NOT IN ('completed', 'failed', 'cancelled', 'uploaded')
        RETURNING id, status, error_message
    """)).fetchall()

print(f"Reset {len(result)} stuck job(s):")
for row in result:
    print(f"  id={row[0]} -> status={row[1]}")
