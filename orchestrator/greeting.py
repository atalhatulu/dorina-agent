"""Greeting detection — selamlama mesajlarini tespit eder."""

from __future__ import annotations
from typing import Optional

_GREETING_WORDS = {
    "merhaba", "selam", "hey", "hi", "hello", "naber",
    "nasilsin", "nasılsın", "gunaydin", "günaydın",
    "iyi geceler", "kolay gelsin", "ne haber",
}


def is_greeting(text: Optional[str]) -> bool:
    """Sadece selamlamadan olusan mesajlari tespit et.

    Args:
        text: Kullanicinin gonderdigi ham mesaj.

    Returns:
        True eger mesaj sadece selamlama kelimelerinden olusuyorsa (en fazla 3 kelime).
    """
    cleaned = (text or "").lower().strip().rstrip(".!?,")
    if not cleaned:
        return False

    # Multi-word greetings (2+ kelimeli selamlamalar)
    _multi_word_greetings = {"iyi geceler", "kolay gelsin", "ne haber"}
    if cleaned in _multi_word_greetings:
        return True

    # Single-word greeting check: tum kelimeler selamlama kumesinde mi?
    words = cleaned.split()
    _allowed_single = _GREETING_WORDS | {"talha", "dorina"}
    return len(words) <= 3 and all(w in _allowed_single for w in words)
