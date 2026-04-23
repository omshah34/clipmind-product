"""File: db/connection.py
Purpose: SQLAlchemy database engine and session setup.
         Creates database connection pool and session factory for all queries.
         Falls back to local SQLite.

Gap 30: Celery workers must not share a QueuePool across fork() boundaries.
         When CELERY_WORKER_RUNNING=1 the engine is created with NullPool so
         each task opens and closes its own connection atomically, avoiding
         'SSL connection has been closed unexpectedly' and pool exhaustion.

The schema bootstrap used to run on import, but that made Celery worker/beat
startup fail hard when the database was not yet available. Schema creation is
now explicit via scripts/setup_db.py.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

from core.config import settings

logger = logging.getLogger(__name__)

# Primary Data Source
db_url = settings.database_url

if not db_url:
    logger.warning("DATABASE_URL not configured. Defaulting to local SQLite.")
    db_url = "sqlite:///clipmind_dev.db"

logger.info("Connecting to database: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

# Gap 30: Celery workers use NullPool to avoid sharing pool state across fork()
_is_celery_worker = os.environ.get("CELERY_WORKER_RUNNING") == "1"

if _is_celery_worker:
    logger.info("Celery worker detected — using NullPool to prevent connection sharing (Gap 30)")
    engine = create_engine(
        db_url,
        poolclass=NullPool,  # Each task opens/closes its own connection
        pool_pre_ping=True,
        future=True,
    )
else:
    # FastAPI: Production-tuned QueuePool for concurrent request handling
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=10,         # Base persistent connections per process
        max_overflow=20,      # Extra burst connections allowed
        pool_recycle=300,     # Recycle stale connections every 5 minutes
        pool_timeout=30,      # Raise error after 30s waiting for a connection
        future=True,
    )

# Session factory for use in FastAPI Depends() or manually
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True
)


def initialize_database() -> None:
    """Explicitly create schema tables and seed local-dev data."""
    from db.init_db import init_db_tables

    try:
        init_db_tables(engine)
        logger.info("Database connection and schema initialization successful.")
    except Exception:
        logger.exception("Error during schema initialization")
