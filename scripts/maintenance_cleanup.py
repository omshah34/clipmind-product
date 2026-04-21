"""File: maintenance_cleanup.py
Purpose: One-time utility to purge all data associated with the legacy mock user ID.
         Ensures a clean slate for the multi-tenant production launch.
"""

import logging
from db.connection import engine
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MOCK_USER_ID = "00000000-0000-0000-0000-000000000000"

def purge_mock_data():
    queries = [
        "DELETE FROM dna_learning_logs WHERE user_id = :user_id",
        "DELETE FROM content_signals WHERE user_id = :user_id",
        "DELETE FROM user_score_weights WHERE user_id = :user_id",
        "DELETE FROM dna_executive_summaries WHERE user_id = :user_id",
        "DELETE FROM connected_sources WHERE user_id = :user_id",
        "DELETE FROM performance_alerts WHERE user_id = :user_id",
        "DELETE FROM publish_queue WHERE job_id IN (SELECT CAST(id AS TEXT) FROM jobs WHERE user_id = :user_id)",
        "DELETE FROM clip_performance WHERE job_id IN (SELECT CAST(id AS TEXT) FROM jobs WHERE user_id = :user_id)",
        "DELETE FROM jobs WHERE user_id = :user_id",
    ]
    
    logger.info("Starting purge of data for mock user: %s", MOCK_USER_ID)
    
    # Use connection and execute separately to avoid poisoned transactions in a begin block
    with engine.connect() as connection:
        for idx, q_str in enumerate(queries):
            try:
                # Wrap each in its own transaction
                with connection.begin():
                    result = connection.execute(text(q_str), {"user_id": MOCK_USER_ID})
                    logger.info("Query %d executed. Rows affected: %d", idx + 1, result.rowcount)
            except Exception as e:
                logger.error("Query %d failed: %s", idx + 1, e)

    logger.info("Purge complete.")

if __name__ == "__main__":
    purge_mock_data()
