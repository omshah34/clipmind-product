"""File: services/visual_engine.py
Purpose: NLP-based keyword extraction for deterministic emoji/icon overlays.
"""

from __future__ import annotations

import re
import logging

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
        # In a real app, this would use httpx to call Pexels API
        # Example: https://api.pexels.com/videos/search?query=nature&per_page=1
        import random
        
        # Mock results for Phase 3 implementation
        # Real implementation would require PEXELS_API_KEY in .env
        mock_clips = [
            {"id": "b1", "url": "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_1mb.mp4", "preview": "Finance"},
            {"id": "b2", "url": "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_2mb.mp4", "preview": "Growth"},
            {"id": "b3", "url": "https://sample-videos.com/video123/mp4/720/big_buck_bunny_720p_5mb.mp4", "preview": "AI"}
        ]
        
        logger.info("Found contextual B-Roll for keywords: %s", keywords)
        return random.sample(mock_clips, min(len(mock_clips), count))
