"""File: tests/test_ass_generator.py
Purpose: Unit tests for the ASS styling engine.
"""

import unittest
from pathlib import Path
from services.ass_generator import ASSGenerator

class TestASSGenerator(unittest.TestCase):

    def setUp(self):
        self.dummy_words = [
            {"word": "Hello", "start": 0.0, "end": 0.5, "probability": 0.95},
            {"word": "world", "start": 0.5, "end": 1.0, "probability": 0.98},
            {"word": "this", "start": 1.0, "end": 1.5, "probability": 0.92},
            {"word": "is", "start": 1.5, "end": 2.0, "probability": 0.99},
            {"word": "viral", "start": 2.0, "end": 2.5, "probability": 0.97},
        ]

    def test_hormozi_generation(self):
        """Should generate Hormozi style with All-Caps and highlighting."""
        gen = ASSGenerator(preset_name="hormozi")
        ass_content = gen.words_to_ass(self.dummy_words, max_words_per_line=3)
        
        # Check for highlighting tags (Primary: &HFFFFFF&, Secondary: &H00FFFF&)
        self.assertIn("{\\1c&H00FFFF&}HELLO", ass_content)
        self.assertIn("{\\1c&HFFFFFF&}WORLD", ass_content)
        
        # Check for multiple Dialogue lines (word-by-word)
        lines = [l for l in ass_content.split("\n") if l.startswith("Dialogue:")]
        self.assertEqual(len(lines), 5) # 5 words = 5 events

    def test_mrbeast_generation(self):
        """Should generate MrBeast style with correct font and color."""
        gen = ASSGenerator(preset_name="mrbeast")
        header = gen.generate_header()
        self.assertIn("Arial Black", header) 
        self.assertIn("&H00FFFF&", header) # Primary Yellow
        
        ass_content = gen.words_to_ass(self.dummy_words)
        self.assertIn("{\\1c&H00FF00&}Hello", ass_content) # Green highlight (Original Case)

    def test_confidence_fallback(self):
        """Should fallback to line-level if confidence is low."""
        low_conf_words = [
            {"word": "fuzzy", "start": 0.0, "end": 1.0, "probability": 0.1},
            {"word": "speech", "start": 1.0, "end": 2.0, "probability": 0.2},
        ]
        gen = ASSGenerator(preset_name="hormozi")
        ass_content = gen.words_to_ass(low_conf_words)
        
        # Should NOT have highlighting tags in fallback
        self.assertNotIn("{\\1c", ass_content)
        
        # Should have 1 Dialogue line for the chunk instead of 2
        lines = [l for l in ass_content.split("\n") if l.startswith("Dialogue:")]
        self.assertEqual(len(lines), 1)

    def test_framing_protection(self):
        """Should apply MarginV correctly based on preset."""
        gen = ASSGenerator(preset_name="hormozi")
        header = gen.generate_header()
        # MarginV for Hormozi is 150
        self.assertIn(",10,10,150,1", header)

if __name__ == "__main__":
    unittest.main()
