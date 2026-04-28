from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import get_type_hints
from uuid import uuid4
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies.auth import AuthenticatedUser, get_current_user
from api.models.preview_studio import RenderRequest
from api.routes import preview_studio


def _build_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(preview_studio.router, prefix="/api/v1")

    async def _user_override() -> AuthenticatedUser:
        return AuthenticatedUser(
            user_id="00000000-0000-0000-0000-000000000000",
            email="local@clipmind.com",
            role="owner",
        )

    app.dependency_overrides[get_current_user] = _user_override
    return TestClient(app)


def test_preview_render_route_uses_shared_render_request_model() -> None:
    assert get_type_hints(preview_studio.create_preview_render)["payload"] is RenderRequest


def test_preview_render_persists_override_recipe() -> None:
    client = _build_test_client()
    clip = SimpleNamespace(
        start_time=0.0,
        end_time=8.0,
        render_recipe={
            "layout_type": "vertical",
            "screen_focus": "center",
            "selected_hook": "Base hook",
            "caption_preset": "hormozi",
            "caption_enabled": True,
            "subject_centers": [640.0],
            "audio_profile": "loudnorm_i_-14",
            "watermark_enabled": False,
        },
    )
    job = SimpleNamespace(
        id=uuid4(),
        user_id="00000000-0000-0000-0000-000000000000",
        status="completed",
        transcript_json={"words": []},
        clips_json=[clip],
    )
    render_job_id = uuid4()

    with patch("api.routes.preview_studio.get_job", return_value=job), patch(
        "api.routes.preview_studio.create_render_job",
        return_value={"id": render_job_id, "created_at": datetime.now(timezone.utc)},
    ) as create_render_job_mock, patch("api.routes.preview_studio.dispatch_task") as dispatch_task_mock:
        response = client.post(
            f"/api/v1/preview/{job.id}/0/render",
            json={
                "edited_srt": "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
                "caption_style": {"font": "Arial"},
                "layout_type": "speaker_screen",
                "hook_text": " Override hook ",
                "screen_focus": "right",
                "caption_preset": " karaoke ",
                "caption_enabled": False,
            },
        )

    assert response.status_code == 202
    kwargs = create_render_job_mock.call_args.kwargs
    assert kwargs["edited_srt"] == "1\n00:00:00,000 --> 00:00:01,000\nhello"
    assert kwargs["caption_style"] == {"font": "Arial"}
    assert kwargs["render_recipe"]["layout_type"] == "speaker_screen"
    assert kwargs["render_recipe"]["screen_focus"] == "right"
    assert kwargs["render_recipe"]["selected_hook"] == "Override hook"
    assert kwargs["render_recipe"]["caption_preset"] == "karaoke"
    assert kwargs["render_recipe"]["caption_enabled"] is False
    dispatch_task_mock.assert_called_once()


def test_preview_render_request_rejects_invalid_override_values() -> None:
    client = _build_test_client()
    job = SimpleNamespace(
        id=uuid4(),
        user_id="00000000-0000-0000-0000-000000000000",
        status="completed",
        transcript_json={"words": []},
        clips_json=[SimpleNamespace(start_time=0.0, end_time=8.0, render_recipe={})],
    )

    with patch("api.routes.preview_studio.get_job", return_value=job), patch(
        "api.routes.preview_studio.create_render_job"
    ) as create_render_job_mock:
        response = client.post(
            f"/api/v1/preview/{job.id}/0/render",
            json={
                "edited_srt": "1\n00:00:00,000 --> 00:00:01,000\nhello\n",
                "layout_type": "wide",
                "screen_focus": "far-right",
            },
        )

    assert response.status_code == 422
    create_render_job_mock.assert_not_called()
