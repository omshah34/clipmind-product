"""File: scripts/setup_db.py
Purpose: Simplified database initialization for new developers.
"""
import sys
import os
from sqlalchemy import create_engine

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.init_db import init_db_tables
from core.config import settings

def main():
    print("⏳ Initializing ClipMind database...")
    try:
        engine = create_engine(settings.database_url)
        init_db_tables(engine)
        print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Failed to initialize database: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
