"""File: workers/dna_tasks.py
Purpose: DNA-related background tasks (Synthesis, etc.)
"""
from workers.celery_app import celery_app
from services.dna.executive_summarizer import get_executive_summarizer
import asyncio
import logging

logger = logging.getLogger(__name__)

@celery_app.task(name="workers.dna_tasks.generate_all_executive_summaries")
def generate_all_executive_summaries():
    """Iterate through all active users and generate their weekly summaries."""
    from db.repositories.users import list_active_users
    users = list_active_users()
    logger.info(f"Generating weekly summaries for {len(users)} users.")
    for user in users:
        generate_executive_summary.delay(str(user["id"]))

@celery_app.task(name="workers.dna_tasks.generate_executive_summary")
def generate_executive_summary(user_id: str):
    """Synthesize DNA logs into a strategic summary."""
    logger.info(f"Starting Executive Summary generation for user {user_id}")
    summarizer = get_executive_summarizer()
    
    # Run the async summarizer
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # If we are inside an existing loop (rare for celery worker but possible)
        import nest_asyncio
        nest_asyncio.apply()
    
    result = loop.run_until_complete(summarizer.generate_summary(user_id))
    
    if result:
        logger.info(f"Executive Summary generated: {result['id']}")
        return result["id"]
    else:
        logger.info("No summary generated (possibly no logs in window).")
        return None
