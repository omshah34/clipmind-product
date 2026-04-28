from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from db.repositories import render_jobs


def _row(mapping: dict) -> MagicMock:
    row = MagicMock()
    row._mapping = mapping
    return row


def test_create_render_job_deserializes_render_recipe_json() -> None:
    render_job_id = uuid4()
    fake_row = _row(
        {
            "id": str(render_job_id),
            "edited_style": '{"font":"Arial"}',
            "render_recipe_json": '{"layout_type":"speaker_screen","screen_focus":"right"}',
        }
    )
    connection = MagicMock()
    connection.execute.return_value.fetchone.return_value = fake_row
    begin_ctx = MagicMock()
    begin_ctx.__enter__.return_value = connection
    begin_ctx.__exit__.return_value = None

    with patch.object(render_jobs.engine, "begin", return_value=begin_ctx):
        created = render_jobs.create_render_job(
            user_id=uuid4(),
            job_id=uuid4(),
            clip_index=0,
            edited_srt="1\n00:00:00,000 --> 00:00:01,000\nhi\n",
            caption_style={"font": "Arial"},
            render_recipe={"layout_type": "speaker_screen", "screen_focus": "right"},
        )

    assert created is not None
    assert created["edited_style"]["font"] == "Arial"
    assert created["render_recipe_json"]["layout_type"] == "speaker_screen"


def test_get_and_list_render_jobs_preserve_json_structure() -> None:
    row_mapping = {
        "id": str(uuid4()),
        "status": "queued",
        "progress_percent": 0,
        "created_at": datetime.now(timezone.utc),
        "edited_style": '{"font":"Arial"}',
        "render_recipe_json": '{"layout_type":"vertical","caption_enabled":true}',
    }
    fetch_one_connection = MagicMock()
    fetch_one_connection.execute.return_value.fetchone.return_value = _row(row_mapping)
    fetch_all_connection = MagicMock()
    fetch_all_connection.execute.return_value.fetchall.return_value = [_row(row_mapping)]

    single_ctx = MagicMock()
    single_ctx.__enter__.return_value = fetch_one_connection
    single_ctx.__exit__.return_value = None
    list_ctx = MagicMock()
    list_ctx.__enter__.return_value = fetch_all_connection
    list_ctx.__exit__.return_value = None

    with patch.object(render_jobs.engine, "begin", side_effect=[single_ctx, list_ctx]):
        fetched = render_jobs.get_render_job(uuid4())
        listed = render_jobs.list_render_jobs(uuid4())

    assert fetched is not None
    assert fetched["render_recipe_json"]["caption_enabled"] is True
    assert listed[0]["edited_style"]["font"] == "Arial"
    assert listed[0]["render_recipe_json"]["layout_type"] == "vertical"
