"""Tests for orchestrator/greeting.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from orchestrator.greeting import is_greeting


class TestIsGreeting:
    def test_basic_turkish_greeting(self):
        assert is_greeting("merhaba") is True

    def test_english_greeting(self):
        assert is_greeting("hello") is True
        assert is_greeting("hi") is True

    def test_greeting_with_name(self):
        assert is_greeting("merhaba talha") is True

    def test_multi_word_greeting(self):
        assert is_greeting("iyi geceler") is True
        assert is_greeting("kolay gelsin") is True

    def test_greeting_with_punctuation(self):
        assert is_greeting("Merhaba!") is True
        assert is_greeting("Selam?") is True
        assert is_greeting("hey,") is True

    def test_not_a_greeting(self):
        assert is_greeting("bugun hava cok guzel") is False
        assert is_greeting("read file /etc/passwd") is False

    def test_too_many_words_fails(self):
        # 4+ greeting words fails the <=3 check
        assert is_greeting("merhaba selam hey hello") is False

    def test_empty_text(self):
        assert is_greeting("") is False
        assert is_greeting(None) is False

    def test_dorina_greeting(self):
        assert is_greeting("dorina") is True
        assert is_greeting("selam dorina") is True

    def test_various_turkish_greetings(self):
        for g in ["selam", "naber", "nasilsin", "nasılsın", "gunaydin", "günaydın", "ne haber"]:
            assert is_greeting(g) is True, f"{g} should be detected as greeting"
