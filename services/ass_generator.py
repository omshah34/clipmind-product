"""File: services/ass_generator.py
Purpose: Config-driven generation of Advanced Substation Alpha (.ass) subtitles.
         Supports word-by-word highlighting and viral style presets.
"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class ASSStyle:
    font_name: str
    font_size: int
    primary_color: str  # &HBBGGRR&
    secondary_color: str
    outline_color: str
    back_color: str
    bold: int = 1
    italic: int = 0
    alignment: int = 2  # Bottom Center
    margin_v: int = 100
    outline: int = 2
    shadow: int = 0
    uppercase: bool = False

# Legally safe Google Font equivalents
PRESETS = {
    "hormozi": ASSStyle(
        font_name="Impact",  # Standard, High Impact
        font_size=24,
        primary_color="&HFFFFFF&",   # White
        secondary_color="&H00FFFF&", # Yellow highlight
        outline_color="&H000000&",   # Black
        back_color="&H000000&",
        uppercase=True,
        alignment=2,
        margin_v=150,
    ),
    "mrbeast": ASSStyle(
        font_name="Arial Black", # Good proxy for Luckiest Guy if not installed
        font_size=28,
        primary_color="&H00FFFF&",   # Yellow
        secondary_color="&H00FF00&", # Green highlight
        outline_color="&H000000&",   # Black
        back_color="&H000000&",
        outline=4,
        margin_v=120,
    ),
    "minimalist": ASSStyle(
        font_name="Inter",
        font_size=20,
        primary_color="&HFFFFFF&",
        secondary_color="&HAAAAAA&", # Soft grey highlight
        outline_color="&H000000&",
        back_color="&H000000&",
        bold=0,
        outline=1,
        margin_v=80,
    )
}

def format_ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100) # Centiseconds for ASS
    return f"{h}:{m:02}:{s:02}.{cs:02}"

class ASSGenerator:
    def __init__(self, preset_name: str = "hormozi"):
        self.style = PRESETS.get(preset_name.lower(), PRESETS["hormozi"])

    def generate_header(self) -> str:
        s = self.style
        header = [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "ScaledBorderAndShadow: yes",
            "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            f"Style: Default,{s.font_name},{s.font_size},{s.primary_color},{s.secondary_color},{s.outline_color},{s.back_color},{s.bold},{s.italic},0,0,100,100,0,0,1,{s.outline},{s.shadow},{s.alignment},10,10,{s.margin_v},1",
            "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        return "\n".join(header)

    def words_to_ass(self, words: list[dict], transients: list[float] | None = None, max_chars_per_line: int = 18) -> str:
        """
        Converts word-level transcript data into word-by-word highlighted Dialogue lines.
        Uses character-aware wrapping to prevent mobile overflow (Gap 104).
        """
        if not words:
            return ""

        from services.visual_engine import VisualEngine

        # Group words into chunks that fit on screen
        chunks: list[list[dict]] = []
        current_chunk: list[dict] = []
        current_len = 0
        
        for w in words:
            word_text = w["word"].strip()
            # If word is very long or current line is full, start new chunk
            if current_len + len(word_text) > max_chars_per_line and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_len = 0
            
            current_chunk.append(w)
            current_len += len(word_text) + 1
            
            # Max 2-3 words per line is still a good viral "rule of thumb"
            if len(current_chunk) >= 3:
                chunks.append(current_chunk)
                current_chunk = []
                current_len = 0
        
        if current_chunk:
            chunks.append(current_chunk)

        dialogue_lines = []
        for chunk in chunks:
            for j, target_word in enumerate(chunk):
                start_raw = float(target_word["start"])
                end_raw = float(target_word["end"])
                
                if transients:
                    for t in transients:
                        if abs(t - start_raw) < 0.100:
                            start_raw = t
                            break

                start = format_ass_time(start_raw)
                end = format_ass_time(end_raw)
                
                line_text = ""
                for k, w in enumerate(chunk):
                    word_text = w["word"].strip()
                    emoji = VisualEngine.get_emoji_for_word(word_text)
                    
                    if self.style.uppercase:
                        word_text = word_text.upper()
                        
                    if k == j:
                        # HIGHLIGHTED WORD
                        pop_tags = "{\\fscx115\\fscy115\\t(0,80,\\fscx100\\fscy100)}"
                        color_tag = f"{{\\1c{self.style.secondary_color}}}"
                        display_text = f"{pop_tags}{color_tag}{word_text}"
                        if emoji:
                            display_text += f" {emoji}"
                        line_text += f"{display_text} "
                    else:
                        # NORMAL WORD
                        color_tag = f"{{\\1c{self.style.primary_color}}}"
                        line_text += f"{color_tag}{word_text} "
                
                dialogue_lines.append(
                    f"Dialogue: 0,{start},{end},Default,,0,0,0,,{line_text.strip()}"
                )
        
        return "\n".join(dialogue_lines)

    def _generate_line_level(self, words: list[dict], max_words_per_line: int = 3) -> str:
        """Simple line-by-line fallback without word highlighting."""
        dialogue_lines = []
        for i in range(0, len(words), max_words_per_line):
            chunk = words[i : i + max_words_per_line]
            start = format_ass_time(chunk[0]["start"])
            end = format_ass_time(chunk[-1]["end"])
            text = " ".join(w["word"].strip() for w in chunk)
            if self.style.uppercase:
                text = text.upper()
            dialogue_lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
        return "\n".join(dialogue_lines)

    def create_ass_file(self, words: list[dict], output_path: Path, transients: list[float] | None = None):
        content = self.generate_header() + "\n" + self.words_to_ass(words, transients=transients)
        output_path.write_text(content, encoding="utf-8")
        return output_path
