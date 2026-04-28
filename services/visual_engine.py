"""File: services/visual_engine.py
Purpose: NLP-based keyword extraction for deterministic emoji/icon overlays.
"""

from __future__ import annotations

import re
import logging

from core.config import settings

logger = logging.getLogger(__name__)

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

# Mapping keywords to Pexels search queries for B-Roll
VISUAL_CATEGORY_MAP = {
    "money": ["finance", "luxury", "cash"],
    "growth": ["nature", "growth", "charts", "startup"],
    "ai": ["technology", "circuit", "robot", "futuristic"],
    "business": ["office", "meeting", "shaking hands", "corporate"],
    "emotions": ["laughing", "surprised", "angry", "crying"],
    "generic": ["abstract", "particles", "cityscape"]
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

    @staticmethod
    async def find_contextual_broll(keywords: list[str], count: int = 3) -> list[dict]:
        """
        Searches Pexels for B-Roll clips based on extracted keywords.
        Gap Exploited: Visual boredom in long-form talking heads.
        """
        if not settings.enable_contextual_broll:
            return []

        if not settings.pexels_api_key:
            logger.info("Contextual B-roll enabled but PEXELS_API_KEY is not configured; skipping.")
            return []

        # Provider integration intentionally returns no clips until the download
        # path can enforce licensing, duration, and timeout constraints.
        logger.info("Contextual B-roll provider configured but no provider adapter is active; skipping.")
        return []
