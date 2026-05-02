"""File: services/visual_engine.py
Purpose: NLP-based keyword extraction for deterministic emoji/icon overlays.
"""

from __future__ import annotations

import re
import logging

import httpx

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

        query_terms = [term.strip() for term in keywords if term and term.strip()]
        query = " ".join(query_terms[:3]) or "abstract business"
        params = {
            "query": query,
            "per_page": max(1, min(count, 15)),
            "orientation": "landscape",
        }
        headers = {"Authorization": settings.pexels_api_key}

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{settings.pexels_api_base_url.rstrip('/')}/videos/search",
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:
            logger.warning("Contextual B-roll search failed for query %r: %s", query, exc)
            return []

        results: list[dict] = []
        for video in payload.get("videos", [])[:count]:
            video_files = video.get("video_files", []) or []
            if not video_files:
                continue

            chosen_file = sorted(
                video_files,
                key=lambda item: (item.get("width", 0) * item.get("height", 0), item.get("file_size", 0)),
                reverse=True,
            )[0]
            link = chosen_file.get("link")
            if not link:
                continue

            results.append(
                {
                    "id": video.get("id"),
                    "url": link,
                    "thumbnail": video.get("image"),
                    "duration": video.get("duration"),
                    "width": chosen_file.get("width"),
                    "height": chosen_file.get("height"),
                    "source": "pexels",
                    "query": query,
                }
            )

        return results
