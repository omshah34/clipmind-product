from services.render_recipe import build_render_recipe, merge_render_recipe, pick_hook_text


def test_pick_hook_text_falls_back_to_transcript_excerpt():
    clip = {"hook_headlines": [], "reason": ""}
    transcript = {
        "words": [
            {"word": "this", "start": 0.0, "end": 0.2},
            {"word": "is", "start": 0.2, "end": 0.4},
            {"word": "the", "start": 0.4, "end": 0.6},
            {"word": "fallback", "start": 0.6, "end": 0.8},
            {"word": "hook", "start": 0.8, "end": 1.0},
            {"word": "text", "start": 1.0, "end": 1.2},
            {"word": "extra", "start": 1.2, "end": 1.4},
        ]
    }

    assert pick_hook_text(clip, transcript, 0.0, 2.0) == "this is the fallback hook text"


def test_build_render_recipe_uses_screen_only_when_no_faces_detected():
    recipe = build_render_recipe(
        {"hook_headlines": ["Hook"], "reason": "Reason"},
        transcript_json=None,
        clip_start_time=0.0,
        clip_end_time=5.0,
        subject_centers=[],
        detected_face_count=0,
        primary_face_area_ratio=None,
    )

    assert recipe["visual_mode"] == "screen_demo"
    assert recipe["layout_type"] == "screen_only"


def test_merge_render_recipe_applies_overrides_and_preserves_caption_enabled():
    recipe = merge_render_recipe(
        {
            "visual_mode": "face_cam",
            "layout_type": "vertical",
            "subject_centers": [960.0],
            "screen_focus": "center",
            "selected_hook": "Base hook",
            "caption_preset": "hormozi",
            "caption_enabled": True,
            "watermark_enabled": True,
            "audio_profile": "loudnorm_i_-14",
        },
        {
            "layout_type": "speaker_screen",
            "hook_text": "Override hook",
            "screen_focus": "right",
            "caption_enabled": False,
        },
    )

    assert recipe["layout_type"] == "speaker_screen"
    assert recipe["visual_mode"] == "screen_demo"
    assert recipe["selected_hook"] == "Override hook"
    assert recipe["screen_focus"] == "right"
    assert recipe["caption_enabled"] is False
