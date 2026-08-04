"""Akıllı Query Classification (puan tabanlı deterministik)."""

import re

CATEGORIES = ("read", "chat", "code", "general")

READ_CONCEPTS = [
    "hava durumu", "weather", "haber", "news", "nedir", "ne demek", 
    "nasil yapilir", "what is", "who is", "where", "saat kac", "fiyat", "kac", 
    "download", "oku", "search", "istatistik", "nufus", "tarih", "gundem"
]
READ_CONCEPTS_REGEX = re.compile(r"\b(" + "|".join(READ_CONCEPTS).replace(" ", r"\s+") + r")\b", re.IGNORECASE)

READ_QUESTION_REGEX = re.compile(r"\b(ne|kim|nerede|kac|nasil|neden|when|where|who|how|how much)\b.*?\b(is|are|oldugu|olduğu)\b", re.IGNORECASE)

CODE_CMD_VERBS = [
    "yaz", "olustur", "create", "build", "compile", "calistir", "run", "kur", "install",
    "duzelt", "fix", "hata", "debug", "test", "patch", "refactor", "fonksiyon", "script", 
    "class", "import", "dosya", "klasor", "dizin", "python"
]
CODE_CMD_REGEX = re.compile(r"\b(" + "|".join(CODE_CMD_VERBS) + r")\b", re.IGNORECASE)

CODE_PATH_REGEX = re.compile(r"(\.(py|sh|md|rs|go|js|ts)\b|~/)")
CODE_TEMPLATE_REGEX = re.compile(r"\b(yaz|olustur|uret|kur|calistir|duzelt)\b.*?\b(kod|script|dosya|fonksiyon)\b|\b(kod|script|dosya|fonksiyon)\b.*?\b(yaz|olustur|uret|kur|calistir|duzelt)\b", re.IGNORECASE)
CODE_TOOL_REGEX = re.compile(r"\b(grep|liste|tara|say|kac tane|dosyada ara)\b", re.IGNORECASE)

CHAT_PATTERNS = {"merhaba", "selam", "hey", "nasilsin", "naber", "tesekkur", "thanks", "gorusuruz", "bye", "hello"}

def score_greeting(text: str) -> float:
    score = 0.0
    words = [w.strip(".,!?") for w in text.split()]
    
    if words and all(w in CHAT_PATTERNS for w in words):
        score += 3.0
    
    if len(words) <= 2 and not any(c in text for c in (".", "/", "\\", "=", ">", "&")):
        score += 1.5
        
    if "?" not in text and len(text) < 20:
        score += 0.5
        
    return score

def score_read(text: str) -> float:
    score = 0.0
    
    matches = READ_CONCEPTS_REGEX.findall(text)
    score += 1.0 * len(matches)
    
    if READ_QUESTION_REGEX.search(text):
        score += 1.5
        
    words = text.split()
    if len(words) <= 10 and "python" not in text and "api" not in text:
        score += 0.7
        
    if not CODE_CMD_REGEX.search(text):
        score += 0.5
        
    return score

def score_code(text: str) -> float:
    score = 0.0
    
    matches = CODE_CMD_REGEX.findall(text)
    score += 1.0 * len(matches)
    
    if CODE_PATH_REGEX.search(text):
        score += 1.5
        
    if CODE_TEMPLATE_REGEX.search(text):
        score += 2.0
        
    if any(c in text for c in (".", "/", "&", ">", "|")):
        score += 0.8
        
    if CODE_TOOL_REGEX.search(text):
        score += 1.0
        
    return score

def classify(user_input: str) -> str:
    """Puan tabanlı sınıflandırma."""
    if user_input is None or not str(user_input).strip():
        return "general"
        
    text = str(user_input).lower().strip()
    
    scores = {
        "chat": score_greeting(text),
        "read": score_read(text),
        "code": score_code(text),
        "general": 0.0
    }
    
    priorities = {"read": 4, "code": 3, "general": 2, "chat": 1}
    best = max(scores.items(), key=lambda x: (x[1], priorities[x[0]]))
    
    return best[0]
