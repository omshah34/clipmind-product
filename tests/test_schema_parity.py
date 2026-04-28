from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from core.config import settings
from db.init_db import init_db_tables


def _alembic_config() -> Config:
    return Config("db/alembic.ini")


def test_sqlite_fresh_schema_includes_clips_and_render_job_columns() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "schema_test.sqlite3"
        engine = create_engine(f"sqlite:///{db_path}")

        init_db_tables(engine)

        connection = sqlite3.connect(db_path)
        try:
            clips_cols = {row[1] for row in connection.execute("PRAGMA table_info(clips)").fetchall()}
            render_job_cols = {row[1] for row in connection.execute("PRAGMA table_info(render_jobs)").fetchall()}
        finally:
            connection.close()

    assert {"srt_url", "layout_type", "visual_mode", "selected_hook", "render_recipe"} <= clips_cols
    assert {"render_recipe_json", "progress_percent", "error_message"} <= render_job_cols


def test_postgres_schema_declares_clips_projection_table() -> None:
    schema = Path("db/postgres_schema.sql").read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS clips" in schema
    assert "render_recipe    JSONB" in schema
    assert "selected_hook    TEXT" in schema
    assert "visual_mode      TEXT" in schema


def test_alembic_has_single_render_head() -> None:
    script = ScriptDirectory.from_config(_alembic_config())

    assert script.get_heads() == ["5d6d2f1a9b7c"]


def test_alembic_clean_sqlite_upgrade_reaches_head() -> None:
    tmpdir = tempfile.TemporaryDirectory()
    db_path = Path(tmpdir.name) / "alembic_clean.sqlite3"
    original_database_url = settings.database_url
    object.__setattr__(settings, "database_url", f"sqlite:///{db_path}")
    try:
        config = _alembic_config()
        command.upgrade(config, "head")

        connection = sqlite3.connect(db_path)
        try:
            versions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version").fetchall()]
        finally:
            connection.close()
    finally:
        object.__setattr__(settings, "database_url", original_database_url)
        tmpdir.cleanup()

    assert versions == ["5d6d2f1a9b7c"]
