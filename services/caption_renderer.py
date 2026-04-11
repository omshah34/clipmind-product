from __future__ import annotations

from pathlib import Path


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
        encoding="utf-8",
    )
    return output_path
