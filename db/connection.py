"""File: db/connection.py
Purpose: SQLAlchemy database engine and session setup.
         Creates database connection pool and session factory for all queries.
         Falls back to local PostgreSQL configuration.

The schema bootstrap used to run on import, but that made Celery worker/beat
startup fail hard when the database was not yet available. Schema creation is
now explicit via scripts/setup_db.py.
"""

from __future__ import annotations

import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings

logger = logging.getLogger(__name__)

# Primary Data Source
db_url = settings.database_url

if not db_url:
    logger.warning("DATABASE_URL not configured. Defaulting to local SQLite.")
    db_url = "sqlite:///clipmind_dev.db"

# Debug log to catch unexpected Postgres URLs
print(f"DEBUG: Using database URL: {db_url}")
logger.info(f"Connecting to database via SQLAlchemy...")

# Production-tuned Engine for PostgreSQL
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
