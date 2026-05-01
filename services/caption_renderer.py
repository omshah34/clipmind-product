"""File: services/caption_renderer.py
Purpose: Converts Whisper word timestamps into clip-relative SRT captions.
         Burns captions into video using FFmpeg subtitle filter.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from services.ass_generator import ASSGenerator


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def flatten_words(transcript_json: dict | None) -> list[dict]:
    if not transcript_json:
        return []
    if isinstance(transcript_json.get("words"), list):
        return transcript_json["words"]

    words: list[dict] = []
    for segment in transcript_json.get("segments", []):
        words.extend(segment.get("words", []))
    return words


def words_to_srt(words: list, max_words_per_line: int = 4) -> str:
    entries: list[str] = []
    i = 0
    index = 1
    while i < len(words):
        chunk = words[i : i + max_words_per_line]
        start = chunk[0]["start"]
        end = chunk[-1]["end"]
        text = " ".join(word["word"].strip() for word in chunk)
        entries.append(
            f"{index}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{text}\n"
        )
        index += 1
        i += max_words_per_line
    return "\n".join(entries)


def srt_to_words(srt_text: str) -> list[dict]:
    words: list[dict] = []
    blocks = re.split(r"\r?\n\r?\n", srt_text.strip())
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        timing_line = lines[1] if "-->" in lines[1] else lines[0]
        text_lines = lines[2:] if "-->" in lines[1] else lines[1:]
        if "-->" not in timing_line or not text_lines:
            continue
        start_raw, end_raw = [part.strip() for part in timing_line.split("-->")]
        start = _parse_srt_time(start_raw)
        end = _parse_srt_time(end_raw)
        caption_text = " ".join(text_lines)
        tokens = [token for token in caption_text.split() if token.strip()]
        if not tokens:
            continue
        duration = max(end - start, 0.01)
        step = duration / len(tokens)
        for index, token in enumerate(tokens):
            token_start = start + (index * step)
            token_end = end if index == len(tokens) - 1 else start + ((index + 1) * step)
            words.append({"start": token_start, "end": token_end, "word": token})
    return words


def _parse_srt_time(value: str) -> float:
    hours, minutes, seconds_ms = value.split(":")
    seconds, milliseconds = seconds_ms.split(",")
    return (
        (int(hours) * 3600)
        + (int(minutes) * 60)
        + int(seconds)
        + (int(milliseconds) / 1000.0)
    )


def clip_relative_words(
    transcript_json: dict,
    clip_start_time: float,
    clip_end_time: float,
) -> list[dict]:
    words = flatten_words(transcript_json)
    relative_words: list[dict] = []
    for word in words:
        start = float(word["start"])
        end = float(word["end"])
        if end < clip_start_time or start > clip_end_time:
            continue
        relative_words.append(
            {
                "start": max(0.0, start - clip_start_time),
                "end": max(0.0, end - clip_start_time),
                "word": word["word"],
            }
        )
    return relative_words


def write_clip_srt(
    transcript_json: dict,
    clip_start_time: float,
    clip_end_time: float,
    output_path: Path,
    max_words_per_line: int = 4,
) -> Path:
    words = clip_relative_words(transcript_json, clip_start_time, clip_end_time)
    output_path.write_text(
        words_to_srt(words, max_words_per_line=max_words_per_line),
        encoding="utf-8-sig", # Gap 187: Force BOM for Windows compatibility
    )
    return output_path

def write_clip_ass(
    transcript_json: dict,
    clip_start_time: float,
    clip_end_time: float,
    output_path: Path,
    preset_name: str = "hormozi",
    transients: list[float] | None = None,
    layout_type: str = "vertical",
) -> Path:
    words = clip_relative_words(transcript_json, clip_start_time, clip_end_time)
    generator = ASSGenerator(preset_name=preset_name, layout_type=layout_type)
    return generator.create_ass_file(words, output_path, transients=transients)


def write_ass_from_srt(
    srt_text: str,
    output_path: Path,
    *,
    preset_name: str = "hormozi",
    layout_type: str = "vertical",
) -> Path:
    words = srt_to_words(srt_text)
    generator = ASSGenerator(preset_name=preset_name, layout_type=layout_type)
    return generator.create_ass_file(words, output_path)


# Font chain: primary → emoji fallback → last-resort
FONT_CHAIN = [
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

# Local bundled fallbacks
LOCAL_FONTS = {
    "regular": "assets/fonts/NotoSans-Regular.ttf",
    "emoji":   "assets/fonts/NotoColorEmoji.ttf",
    "bold":    "assets/fonts/NotoSans-Bold.ttf",
}

def get_font_path(variant: str = "regular") -> str:
    """Gap 327: Resolve font path with emoji fallbacks."""
    local = LOCAL_FONTS.get(variant)
    if local and os.path.exists(local):
        return local
    # System fallback
    for path in FONT_CHAIN:
        if os.path.exists(path):
            return path
    # Return font name if path not found, FFmpeg might resolve it
    return "Arial"

def contains_emoji(text: str) -> bool:
    """Gap 327: Detect emoji in text."""
    return any(unicodedata.category(c) in ("So", "Mn") for c in text)

def build_drawtext_filter(
    text: str,
    font_path: str,
    font_size: int = 48,
    x: str = "(w-text_w)/2",
    y: str = "h*0.85",
    color: str = "white",
    box_color: str = "black@0.5",
) -> str:
    """
    Gap 322: FFmpeg drawtext with subpixel rendering enabled.
    """
    # Escape special chars in text
    safe_text = (text
        .replace("'", r"\'")
        .replace(":", r"\:")
        .replace(",", r"\,")
    )

    return (
        f"drawtext="
        f"fontfile='{font_path}':"
        f"text='{safe_text}':"
        f"fontsize={font_size}:"
        f"fontcolor={color}:"
        f"x={x}:y={y}:"
        f"borderw=2:"          
        f"bordercolor=black:"
        f"box=1:"
        f"boxcolor={box_color}:"
        f"boxborderw=8:"       
        f"alpha=1"             
    )

def build_caption_filtergraph(drawtext_filter: str) -> str:
    """Gap 322: Ensure 32-bit RGBA pipeline for subpixel accuracy."""
    return f"format=rgba,{drawtext_filter},format=yuv420p"

def build_drawtext_filter_with_emoji(text: str, **kwargs) -> str:
    """Gap 327: Use emoji font when text contains emoji characters."""
    font = get_font_path("emoji" if contains_emoji(text) else "regular")
    return build_drawtext_filter(text, font_path=font, **kwargs)
