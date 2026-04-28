"""Helpers for clip render intent and override resolution."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.caption_renderer import clip_relative_words

VALID_LAYOUT_TYPES = {"vertical", "split_screen", "speaker_screen", "screen_only"}
VALID_SCREEN_FOCUS = {"left", "center", "right"}
DEFAULT_CAPTION_PRESET = "hormozi"
DEFAULT_AUDIO_PROFILE = "loudnorm_i_-14"


def _clean_text(value: Any, max_len: int = 300) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


def transcript_hook_fallback(
    transcript_json: dict | None,
    clip_start_time: float,
    clip_end_time: float,
    *,
    word_limit: int = 6,
) -> str | None:
    words = clip_relative_words(transcript_json or {}, clip_start_time, clip_end_time)
    selected = [str(word.get("word", "")).strip() for word in words if str(word.get("word", "")).strip()]
    if not selected:
        return None
    return " ".join(selected[:word_limit])


def pick_hook_text(
    clip: dict[str, Any],
    transcript_json: dict | None,
    clip_start_time: float,
    clip_end_time: float,
    social_pulse_headline: str | None = None,
) -> str:
    headlines = clip.get("hook_headlines") or []
    if headlines:
        preferred = _clean_text(headlines[0])
        if preferred:
            return preferred

    pulse = _clean_text(social_pulse_headline)
    if pulse:
        return pulse

    reason = _clean_text(clip.get("reason"))
    if reason:
        return reason

    transcript_text = _clean_text(
        transcript_hook_fallback(
            transcript_json,
            clip_start_time,
            clip_end_time,
        )
    )
    if transcript_text:
        return transcript_text

    return "Watch this clip"


def build_render_recipe(
    clip: dict[str, Any],
    *,
    transcript_json: dict | None,
    clip_start_time: float,
    clip_end_time: float,
    subject_centers: list[float] | None = None,
    detected_face_count: int = 0,
    primary_face_area_ratio: float | None = None,
    social_pulse_headline: str | None = None,
    watermark_enabled: bool = False,
) -> dict[str, Any]:
    layout_hint = _clean_text(clip.get("layout_type") or clip.get("layout_suggestion") or "vertical", max_len=64)
    screen_focus = _clean_text(clip.get("screen_focus") or "center", max_len=16) or "center"
    centers = [float(center) for center in (subject_centers or []) if center is not None]

    if layout_hint == "screen_only":
        visual_mode = "screen_demo"
        layout_type = "screen_only"
    elif layout_hint == "speaker_screen":
        visual_mode = "screen_demo"
        layout_type = "speaker_screen"
    elif layout_hint == "split_screen" or detected_face_count >= 2:
        visual_mode = "dual_speaker"
        layout_type = "split_screen"
    elif detected_face_count <= 0:
        visual_mode = "screen_demo"
        layout_type = "screen_only"
    elif primary_face_area_ratio is not None and primary_face_area_ratio < 0.08:
        visual_mode = "screen_demo"
        layout_type = "speaker_screen"
    else:
        visual_mode = "face_cam"
        layout_type = "vertical"

    if layout_type not in VALID_LAYOUT_TYPES:
        layout_type = "vertical"
    if screen_focus not in VALID_SCREEN_FOCUS:
        screen_focus = "center"

    return {
        "visual_mode": visual_mode,
        "layout_type": layout_type,
        "subject_centers": centers,
        "screen_focus": screen_focus,
        "selected_hook": pick_hook_text(
            clip,
            transcript_json,
            clip_start_time,
            clip_end_time,
            social_pulse_headline=social_pulse_headline,
        ),
        "caption_preset": DEFAULT_CAPTION_PRESET,
        "caption_enabled": True,
        "watermark_enabled": bool(watermark_enabled),
        "audio_profile": DEFAULT_AUDIO_PROFILE,
    }


def merge_render_recipe(
    base_recipe: dict[str, Any] | None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    recipe = deepcopy(base_recipe or {})
    recipe.setdefault("visual_mode", "face_cam")
    recipe.setdefault("layout_type", "vertical")
    recipe.setdefault("subject_centers", [])
    recipe.setdefault("screen_focus", "center")
    recipe.setdefault("selected_hook", "Watch this clip")
    recipe.setdefault("caption_preset", DEFAULT_CAPTION_PRESET)
    recipe.setdefault("caption_enabled", True)
    recipe.setdefault("watermark_enabled", False)
    recipe.setdefault("audio_profile", DEFAULT_AUDIO_PROFILE)

    for key, value in (overrides or {}).items():
        if value is None:
            continue
        if key == "hook_text":
            recipe["selected_hook"] = _clean_text(value) or recipe["selected_hook"]
        elif key == "layout_type":
            layout_type = _clean_text(value, max_len=64)
            if layout_type in VALID_LAYOUT_TYPES:
                recipe["layout_type"] = layout_type
        elif key == "screen_focus":
            screen_focus = _clean_text(value, max_len=16)
            if screen_focus in VALID_SCREEN_FOCUS:
                recipe["screen_focus"] = screen_focus
        elif key == "caption_preset":
            recipe["caption_preset"] = _clean_text(value, max_len=64) or recipe["caption_preset"]
        elif key == "caption_enabled":
            recipe["caption_enabled"] = bool(value)
        else:
            recipe[key] = value

    if recipe.get("layout_type") == "split_screen":
        recipe["visual_mode"] = "dual_speaker"
    elif recipe.get("layout_type") in {"speaker_screen", "screen_only"}:
        recipe["visual_mode"] = "screen_demo"
    else:
        recipe["visual_mode"] = "face_cam"

    return recipe
