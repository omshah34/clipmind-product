"""File: bootstrap.py
Purpose: Production orchestration entrypoint.
         Ensures migrations are completed before the application starts.
"""
import sys
import os
import subprocess
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("bootstrap")

def run_migrations():
    """Run Alembic migrations to bring DB to 'head' version."""
    logger.info("Starting database migrations (Alembic)...")
    try:
        # Run alembic upgrade head
        # We capture output to check for errors/logs
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info("Alembic Output:\n%s", result.stdout)
        logger.info("Migrations completed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error("Migrations FAILED with exit code %d", e.returncode)
        logger.error("Error Output:\n%s", e.stderr)
        return False
    except Exception as e:
        logger.error("Unexpected error during migrations: %s", e)
        return False

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "api"
    
    if mode == "migrate":
        # Just run migrations and exit
        success = run_migrations()
        sys.exit(0 if success else 1)
    
    elif mode == "api":
        # Run migrations then start API
        success = run_migrations()
        if not success:
            logger.critical("Migration failed. Blocking API start.")
            sys.exit(1)
        
        logger.info("Starting FastAPI server...")
        os.execvp("uvicorn", ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"])

    elif mode == "worker":
        # Run migrations then start Worker
        success = run_migrations()
        if not success:
            logger.critical("Migration failed. Blocking Worker start.")
            sys.exit(1)
            
        logger.info("Starting Celery worker...")
        os.execvp("celery", ["celery", "-A", "workers.celery_app", "worker", "--loglevel=info", "-P", "solo"])

    else:
        logger.error("Unknown bootstrap mode: %s", mode)
        sys.exit(1)

if __name__ == "__main__":
    main()
