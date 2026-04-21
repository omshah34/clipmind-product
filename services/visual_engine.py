"""File: services/visual_engine.py
Purpose: NLP-based keyword extraction for deterministic emoji/icon overlays.
"""

from __future__ import annotations

import re

# Deterministic mapping for Phase 2 MVP
# Pairs high-impact keywords with viral-style emojis
KEYWORD_EMOJI_MAP = {
    # Finance/Success
    r"\bmoney\b": "💰",
    r"\bcash\b": "💸",
    r"\bprofit\b": "📈",
    r"\brich\b": "🤑",
    r"\bsuccess\b": "🏆",
    
    # Growth/Building
    r"\bgrowth\b": "🌱",
    r"\bbuild\b": "🛠️",
    r"\bbusiness\b": "🏢",
    
    # Emotion/Intensity
    r"\bfire\b": "🔥",
    r"\bdanger\b": "⚠️",
    r"\bsecret\b": "🤫",
    r"\bstop\b": "🛑",
    r"\bwait\b": "⏳",
    
    # Tech/AI
    r"\bai\b": "🤖",
    r"\brobot\b": "🤖",
    r"\bcode\b": "💻",
    
    # Generic Viral
    r"\bwow\b": "😱",
    r"\bamazing\b": "✨",
    r"\bviral\b": "🚀",
}

class VisualEngine:
    @staticmethod
    def get_emoji_for_word(word: str) -> str | None:
        """Returns an emoji if the word matches a viral keyword."""
        clean_word = word.lower().strip(",.?!:;\"'")
        for pattern, emoji in KEYWORD_EMOJI_MAP.items():
            if re.search(pattern, clean_word):
                return emoji
        return None

    @staticmethod
    def tag_transcript_words(words: list[dict]) -> list[dict]:
        """Injects 'emoji' key into word objects if matches are found."""
        tagged_words = []
        for w in words:
            word_text = w.get("word", "")
            emoji = VisualEngine.get_emoji_for_word(word_text)
            tagged_words.append({**w, "emoji": emoji})
        return tagged_words
