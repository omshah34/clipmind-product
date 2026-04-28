"""File: db/connection.py
Purpose: SQLAlchemy database engine and session setup.
         Creates database connection pool and session factory for all queries.
         Falls back to local SQLite.

Gap 30: Celery workers must not share a QueuePool across fork() boundaries.
         When CELERY_WORKER_RUNNING=1 the engine is created with NullPool so
         each task opens and closes its own connection atomically, avoiding
         'SSL connection has been closed unexpectedly' and pool exhaustion.
"""

from __future__ import annotations

import logging
import os
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool
from sqlalchemy.exc import TimeoutError as SQLAlchemyTimeoutError

from core.config import settings
from core.request_context import current_context

logger = logging.getLogger(__name__)

class DatabaseTimeoutException(Exception):
    """Raised when the database connection pool is exhausted."""
    pass

# Primary Data Source
db_url = settings.database_url

if not db_url:
    logger.warning("DATABASE_URL not configured. Defaulting to local SQLite.")
    db_url = "sqlite:///clipmind_dev.db"

logger.info("Connecting to database: %s", db_url.split("@")[-1] if "@" in db_url else db_url)

# Gap 30: Celery workers use NullPool to avoid sharing pool state across fork()
_is_celery_worker = os.environ.get("CELERY_WORKER_RUNNING") == "1"

if _is_celery_worker:
    logger.info("Celery worker detected - using NullPool to prevent connection sharing (Gap 30)")
    engine = create_engine(
        db_url,
        poolclass=NullPool,  # Each task opens/closes its own connection
        pool_pre_ping=True,
    )
else:
    # FastAPI: Production-tuned QueuePool for concurrent request handling
    # Gap 207: DB Connection Resilience. High concurrency pooling.
    # Ensure Postgres max_connections >= 100 on server.
    engine = create_engine(
        db_url,
        pool_pre_ping=True,
        pool_size=20,         # Increased from 10
        max_overflow=40,      # Increased from 20
        pool_recycle=300,     # Recycle stale connections every 5 minutes
        pool_timeout=30,      # 30 seconds wait for a connection
    )

# Session factory for use in FastAPI Depends(get_db)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@event.listens_for(engine, "before_cursor_execute", retval=True)
def _attach_query_trace_comment(conn, cursor, statement, parameters, context, executemany):
    if engine.dialect.name == "sqlite":
        return statement, parameters

    trace = current_context().trace_id
    if not trace or "trace_id=" in statement:
        return statement, parameters

    return f"{statement} /* trace_id={trace} */", parameters

def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
