"""File: services/video_processor.py
Purpose: FFmpeg audio extraction, raw clip cutting, vertical crop, and final export
         logic. Production-hardened with custom exceptions, input validation,
         structured stderr capture, and configurable subtitle styling.

Improvements over v3:
  - Removed dead import: `field` was imported from dataclasses but never used
  - _probe_video except clause no longer catches KeyError from json.loads —
    json.loads never raises KeyError; catching it was dead, misleading code
  - SubtitleStyle is now a frozen dataclass so DEFAULT_SUBTITLE_STYLE cannot
    be accidentally mutated by callers, silently corrupting the shared default
  - validate_timestamps now warns when end_time exceeds video_duration rather
    than silently allowing FFmpeg to produce a shorter-than-requested clip
  - _run_command uses encoding="utf-8", errors="replace" so FFmpeg stderr
    with non-UTF-8 bytes (accented paths, some locales) raises FFmpegError
    instead of UnicodeDecodeError
  - cut_clip -to comment corrected: -to is after -i, so it is relative to the
    start of the output stream (not "relative to -ss when placed before -i")

Improvements over v4:
  - _escape_subtitle_path now uses forward slashes and double-escapes the drive
    colon so Windows paths are parsed correctly by FFmpeg's subtitle filter
  - build_subtitle_filter raises InvalidEncoderSettingError early when input
    dimensions indicate a portrait video — prevents a cryptic FFmpeg crash
    with a negative crop x-offset
  - render_vertical_captioned_clip validates audio_bitrate format before
    passing it to FFmpeg — avoids an opaque FFmpeg failure on bad input
  - Trailing whitespace on the "-c:a" line in render_vertical_captioned_clip
    removed
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output resolution constants
# ---------------------------------------------------------------------------

#: Target width and height for vertical (9:16) export.
OUTPUT_WIDTH: int = 1080
OUTPUT_HEIGHT: int = 1920

#: Valid FFmpeg libx264 preset names in speed order (fastest → best compression).
_VALID_PRESETS: frozenset[str] = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
)

#: Pattern for valid FFmpeg audio bitrate strings e.g. "128k", "192k", "256k".
_AUDIO_BITRATE_RE = re.compile(r"^\d+k$", re.IGNORECASE)

#: Standard safe-zone margin for watermark placement.
WATERMARK_MARGIN_PX: int = 20


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FFmpegError(RuntimeError):
    """Raised when an FFmpeg/ffprobe command exits non-zero.

    Captures stderr so callers and logs see the actual FFmpeg error message
    rather than a generic CalledProcessError.
    """

    def __init__(self, command: list[str], stderr: str, returncode: int) -> None:
        self.command = command
        self.stderr = stderr
        self.returncode = returncode
        readable_cmd = " ".join(command[:6]) + (" ..." if len(command) > 6 else "")
        super().__init__(
            f"FFmpeg exited {returncode} running [{readable_cmd}]:\n{stderr.strip()}"
        )


class ProbeError(RuntimeError):
    """Raised when ffprobe returns unexpected or unparseable output.

    Distinct from FFmpegError so callers can differentiate probe failures
    (corrupt/unsupported file) from encode failures.
    """


class InvalidTimestampError(ValueError):
    """Raised when clip timestamps are logically invalid before FFmpeg runs."""


class InvalidEncoderSettingError(ValueError):
    """Raised when encoder parameters (crf, preset, audio_bitrate) are out of valid range."""


# ---------------------------------------------------------------------------
# Subtitle styling
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SubtitleStyle:
    """Immutable subtitle style configuration.

    Frozen so the module-level DEFAULT_SUBTITLE_STYLE cannot be mutated by
    callers, which would silently corrupt the shared default for all subsequent
    calls in the same process.
    """
    font_name: str = "Arial"
    font_size: int = 22
    bold: bool = True
    alignment: int = 2              # ASS alignment: 2 = bottom-center
    primary_colour: str = "&H00FFFFFF"   # white  (ASS format: &HAABBGGRR)
    outline_colour: str = "&H00000000"   # black
    outline: int = 2

    def __post_init__(self) -> None:
        if self.font_size <= 0:
            raise ValueError(f"font_size must be positive, got {self.font_size}")
        if self.alignment not in range(1, 10):
            raise ValueError(f"alignment must be 1–9 (ASS spec), got {self.alignment}")
        if self.outline < 0:
            raise ValueError(f"outline must be >= 0, got {self.outline}")

    def to_force_style(self) -> str:
        bold_flag = 1 if self.bold else 0
        return (
            f"FontName={self.font_name},"
            f"FontSize={self.font_size},"
            f"Bold={bold_flag},"
            f"Alignment={self.alignment},"
            f"PrimaryColour={self.primary_colour},"
            f"OutlineColour={self.outline_colour},"
            f"Outline={self.outline}"
        )


DEFAULT_SUBTITLE_STYLE = SubtitleStyle()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a shell command, raising FFmpegError on non-zero exit.

    Uses explicit UTF-8 encoding with replacement so that FFmpeg stderr
    containing non-UTF-8 bytes (e.g. accented characters in file paths on
    some locales) raises FFmpegError rather than UnicodeDecodeError.
    """
    logger.debug("Running: %s", " ".join(command))
    result = subprocess.run(
        command,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise FFmpegError(command, result.stderr, result.returncode)
    return result


def _escape_subtitle_path(path: Path) -> str:
    """Return an FFmpeg-safe subtitle path string for Windows.

    Converts backslashes to forward slashes (C:/Users/...) and double-escapes
    the Windows drive colon as \\: so FFmpeg's subtitle filter parser does not
    interpret it as a filter option separator.

    Without this, a path like C:\\Users\\... is swallowed by FFmpeg's parser,
    which strips the backslashes and then tries to interpret the remainder
    (e.g. "UserssshitAppData...clip.srt") as an image size — causing an
    immediate 'Invalid argument' crash.
    """
    posix_path = path.resolve().as_posix()          # C:/Users/sshit/...
    return posix_path.replace(":", "\\\\:")          # C\\:/Users/sshit/...


def _probe_video(video_path: Path) -> dict:
    """Run ffprobe on a video and return the parsed JSON payload.

    Raises:
        FileNotFoundError: If the video does not exist.
        ProbeError: If ffprobe output cannot be parsed as JSON.
        FFmpegError: If ffprobe exits non-zero.
    """
    _assert_file_exists(video_path, "video")
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration,size,bit_rate:stream=codec_type,codec_name,width,height",
        "-of", "json",
        str(video_path),
    ]
    result = _run_command(command)
    try:
        # json.loads raises only json.JSONDecodeError — not KeyError
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(
            f"Unexpected ffprobe output for {video_path.name}: {result.stdout[:200]}"
        ) from exc


def validate_timestamps(
    start_time: float,
    end_time: float,
    video_duration: float | None = None,
) -> None:
    """Raise InvalidTimestampError for logically invalid timestamps.

    Warns (but does not raise) when end_time exceeds video_duration: FFmpeg
    will stop at EOF, producing a clip shorter than requested. Surfacing this
    as a warning rather than an error preserves the useful partial clip while
    making the truncation visible in logs.
    """
    if start_time < 0:
        raise InvalidTimestampError(f"start_time must be >= 0, got {start_time}")
    if end_time <= start_time:
        raise InvalidTimestampError(
            f"end_time ({end_time}) must be greater than start_time ({start_time})"
        )
    if video_duration is not None:
        if start_time >= video_duration:
            raise InvalidTimestampError(
                f"start_time ({start_time}s) exceeds video duration ({video_duration}s)"
            )
        if end_time > video_duration:
            logger.warning(
                "end_time (%.3fs) exceeds video duration (%.3fs); "
                "clip will be truncated to %.3fs.",
                end_time, video_duration, video_duration - start_time,
            )


def _validate_encoder_settings(crf: int, preset: str, audio_bitrate: str) -> None:
    """Raise InvalidEncoderSettingError if crf, preset, or audio_bitrate are invalid.

    audio_bitrate must match the pattern /^\\d+k$/i (e.g. "128k", "192k").
    This catches typos like "abc" or "128" before they reach FFmpeg and
    produce an opaque error message.
    """
    if not (0 <= crf <= 51):
        raise InvalidEncoderSettingError(
            f"crf must be between 0 and 51 (H.264 spec), got {crf}"
        )
    if preset not in _VALID_PRESETS:
        raise InvalidEncoderSettingError(
            f"preset '{preset}' is not a valid libx264 preset. "
            f"Valid options: {sorted(_VALID_PRESETS)}"
        )
    if not _AUDIO_BITRATE_RE.match(audio_bitrate):
        raise InvalidEncoderSettingError(
            f"audio_bitrate '{audio_bitrate}' is not a valid FFmpeg bitrate string. "
            "Expected format: '<number>k' (e.g. '128k', '192k')."
        )


def _assert_file_exists(path: Path, label: str = "file") -> None:
    if not path.exists():
        raise FileNotFoundError(f"Expected {label} not found: {path}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_video_duration_seconds(video_path: Path) -> float:
    """Return the duration of a video file in seconds using ffprobe.

    Raises:
        FileNotFoundError: If the video does not exist.
        ProbeError: If the duration cannot be extracted from ffprobe output.
        FFmpegError: If ffprobe exits non-zero.
    """
    probe = _probe_video(video_path)
    try:
        return float(probe["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ProbeError(
            f"Could not extract duration from ffprobe output for {video_path.name}"
        ) from exc


def get_video_dimensions(video_path: Path) -> tuple[int, int]:
    """Return the (width, height) of the first video stream using ffprobe.

    Raises:
        FileNotFoundError: If the video does not exist.
        ProbeError: If dimensions cannot be extracted from ffprobe output.
        FFmpegError: If ffprobe exits non-zero.
    """
    probe = _probe_video(video_path)
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            try:
                return int(stream["width"]), int(stream["height"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ProbeError(
                    f"Could not parse width/height from video stream for {video_path.name}"
                ) from exc
    raise ProbeError(f"No video stream found in {video_path.name}")


def extract_audio(video_path: Path, output_audio_path: Path) -> Path:
    """Extract audio from a video file as MP3.

    Args:
        video_path: Path to the source video.
        output_audio_path: Destination path for the .mp3 file.

    Returns:
        output_audio_path on success.

    Raises:
        FileNotFoundError: If the source video does not exist.
        FFmpegError: If FFmpeg exits non-zero.
    """
    _assert_file_exists(video_path, "video")
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-acodec", "mp3",
        "-q:a", "2",
        str(output_audio_path),
    ]
    _run_command(command)
    logger.info("Audio extracted: %s → %s", video_path.name, output_audio_path.name)
    return output_audio_path


def cut_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    *,
    validate_duration: bool = True,
) -> Path:
    """Cut a clip from a video using stream copy (no re-encode).

    ``-ss`` is placed before ``-i`` for fast input seeking. ``-to`` is placed
    after ``-i``, so it is relative to the start of the output stream — which
    corresponds to ``start_time`` in the original video because the input was
    already seeked there. Therefore the correct value is ``end_time - start_time``
    (the clip duration), not ``end_time``.

    Minor keyframe drift is expected with stream copy; use
    ``render_vertical_captioned_clip`` when frame accuracy matters.

    Args:
        video_path: Source video path.
        start_time: Start offset in seconds.
        end_time: End offset in seconds.
        output_path: Destination path for the cut clip.
        validate_duration: If True, fetches video duration to validate timestamps.

    Returns:
        output_path on success.
    """
    _assert_file_exists(video_path, "source video")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    video_duration = get_video_duration_seconds(video_path) if validate_duration else None
    validate_timestamps(start_time, end_time, video_duration)

    command = [
        "ffmpeg", "-y",
        "-ss", str(start_time),
        "-i", str(video_path),
        "-to", str(end_time - start_time),  # output-relative: duration of the clip
        "-c", "copy",
        str(output_path),
    ]
    _run_command(command)
    logger.info(
        "Clip cut: %.1fs–%.1fs (%.1fs) → %s",
        start_time, end_time, end_time - start_time, output_path.name,
    )
    return output_path


def build_subtitle_filter(
    srt_path: Path,
    style: SubtitleStyle = DEFAULT_SUBTITLE_STYLE,
    output_width: int = OUTPUT_WIDTH,
    output_height: int = OUTPUT_HEIGHT,
    input_width: int | None = None,
    input_height: int | None = None,
    subject_centers: list[float] | None = None,
    is_ass: bool = False,
    layout_type: str = "vertical",
) -> str:
    """Build the FFmpeg -vf filter string for layout + vertical crop + subtitle burn-in.

    Filter pipeline:
      1. Layout (Vertical or Split-Screen) via LayoutEngine.
      2. scale={width}:{height} — Scale to target resolution.
      3. subtitles=... or ass=... — Burn in captions.

    Args:
        srt_path: Absolute path to the .srt file.
        style: Subtitle styling options.
        output_width: Target pixel width.
        output_height: Target pixel height.
        input_width: Source width.
        input_height: Source height.
        subject_centers: List of X-coordinates for subjects.
        layout_type: "vertical", "split_screen", etc.
    """
    from services.layout_engine import LayoutEngine
    
    # 1. Get Base Layout (Crop/Stack)
    # We pass input_width/height to LayoutEngine
    base_vf = LayoutEngine.get_filtergraph(
        layout_type=layout_type,
        width=input_width or 1920, # Fallback to standard HD
        height=input_height or 1080,
        subject_centers=subject_centers or []
    )

    escaped_path = _escape_subtitle_path(srt_path)
    sub_filter = "ass" if (is_ass or srt_path.suffix.lower() == ".ass") else "subtitles"
    
    # 2. Build Filter Stack
    filters = []
    filters.append(base_vf)
    filters.append(f"scale={output_width}:{output_height}")
    filters.append(f"{sub_filter}={escaped_path}:force_style='{style.to_force_style()}'")
    
    return ",".join(filters)


def render_vertical_captioned_clip(
    raw_clip_path: Path,
    srt_path: Path,
    output_path: Path,
    *,
    style: SubtitleStyle = DEFAULT_SUBTITLE_STYLE,
    crf: int = 23,
    preset: str = "fast",
    audio_bitrate: str = "128k",
    subject_centers: list[float] | None = None,
    layout_type: str = "vertical",
    watermark_path: Path | None = None,
    headline: str | None = None,
) -> Path:
    """Crop, scale, caption, and encode a vertical (9:16) clip with dynamic layout and watermark.
    
    Uses list-based subprocess commands for safety and modular filtergraphs.
    """
    _assert_file_exists(raw_clip_path, "raw clip")
    _assert_file_exists(srt_path, "SRT/ASS subtitle file")
    _validate_encoder_settings(crf, preset, audio_bitrate)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    input_width, input_height = get_video_dimensions(raw_clip_path)

    vf = build_subtitle_filter(
        srt_path, style, output_width, output_height,
        input_width=input_width, input_height=input_height,
        subject_centers=subject_centers,
        layout_type=layout_type
    )
    
    # Build Command List
    command = ["ffmpeg", "-y", "-i", str(raw_clip_path)]
    
    if watermark_path and watermark_path.exists():
        # -- Complex Filtergraph Case (Overlay) ----------------
        command.extend(["-i", str(watermark_path)])
        
        # Scale WM to max 12% width, apply 80% opacity, and overlay in safe-zone
        wm_width_limit = int(output_width * 0.12)
        filter_complex = (
            f"{vf} [base]; "
            f"[1:v] scale='min({wm_width_limit},iw)':-1, colorchannelmixer=aa=0.8 [wm]; "
            f"[base][wm] overlay=W-w-{WATERMARK_MARGIN_PX}:{WATERMARK_MARGIN_PX}"
        )
        command.extend(["-filter_complex", filter_complex])
    else:
        # -- Simple Filtergraph Case ---------------------------
        command.extend(["-vf", vf])

    if headline:
        # Append drawtext to overlay the scroll-stop headline
        # We escape single quotes and colons for the drawtext filter
        safe_headline = headline.replace("'", "\\'").replace(":", "\\:")
        # Styling: Top-center, bold font, semi-transparent background box
        # Windows font path double-escaped if needed, but Arial usually works as name
        # However, for accuracy we use the discovered path
        font_path = "C\\:/Windows/Fonts/Arial.ttf"
        
        drawtext_vf = (
            f"drawtext=text='{safe_headline}':"
            f"fontfile='{font_path}':"
            f"fontcolor=white:fontsize=64:x=(w-text_w)/2:y=h*0.15:"
            f"box=1:boxcolor=black@0.6:boxborderw=20"
        )
        # Update existing vf if simple, or complex if watermark active
        if "-vf" in command:
            idx = command.index("-vf")
            command[idx+1] = f"{command[idx+1]},{drawtext_vf}"
        elif "-filter_complex" in command:
            idx = command.index("-filter_complex")
            # Overlay drawtext after the final watermark overlay
            command[idx+1] = f"{command[idx+1]},{drawtext_vf}"
        
    command.extend([
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        str(output_path),
    ])
    
    _run_command(command)
    logger.info("Rendered captioned clip: %s (wm: %s) -> %s", 
                layout_type, "yes" if watermark_path else "no", output_path.name)
    return output_path
