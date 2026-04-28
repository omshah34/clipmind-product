import os
import sys
from sqlalchemy import text
from db.connection import engine

def run_migration():
    is_sqlite = engine.dialect.name == "sqlite"
    path = "db/migrations/v12_clips_table.sql"
    with open(path, "r") as f:
        sql = f.read()
    
    if is_sqlite:
        print("Detected SQLite dialect - adjusting SQL...")
        sql = sql.replace("gen_random_uuid()", "(lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1, 1) || substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6))))")
        sql = sql.replace("UUID", "TEXT")
        sql = sql.replace("JSONB", "TEXT")
        sql = sql.replace("TIMESTAMPTZ", "TIMESTAMP")
        sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
        # Remove REFERENCES if SQLite doesn't have them yet or keep them if it's fine
        # SQLite supports them but they aren't enforced unless enabled.

    import re
    # Remove single-line comments
    sql = re.sub(r'--.*', '', sql)
    
    # Split by statements
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    
    with engine.begin() as conn:
        for stmt in statements:
            print(f"Executing: {stmt[:50]}...")
            conn.execute(text(stmt))
    print("Migration completed successfully.")

if __name__ == "__main__":
    run_migration()
