"""Otomatik bilgi çıkarımı - konuşmadan önemli bilgileri bul ve kaydet."""

import re
from memory.episodic import EpisodicMemory


class AutoExtractor:
    """Konuşmalardan otomatik bilgi çıkarır."""

    def __init__(self, memory: EpisodicMemory):
        self.memory = memory

    def extract(self, user_message: str, assistant_message: str):
        """Mesajlardan önemli bilgileri çıkar."""
        facts = []

        # User preferences
        pref_patterns = [
            (r"(\w+)\s+(?:kullanıyorum|kullanırım|tercih\s+ederim|kullanır|kullan|kullandığım|severim|sever|seviyorum)", "preference"),
            (r"(?:seviyorum|severim|hoşlanırım|sever)\s+(\w+)", "preference"),
            (r"(?:istemiyorum|sevmiyorum|sevmem)\s+(\w+)", "dislike"),
            (r"(?:kullanıyorum|kullandığım)\s+(\w+)", "tool"),
        ]

        for pattern, category in pref_patterns:
            matches = re.findall(pattern, user_message, re.IGNORECASE)
            for m in matches:
                key = f"pref_{m.lower()}"
                self.memory.save_memory(key, m, category)

        # Projeler
        proj_pattern = r"(?:proje|repo|repository|github)\s*[:\s]*([\w\-\.]+/[\w\-\.]+)"
        matches = re.findall(proj_pattern, user_message + assistant_message, re.IGNORECASE)
        for m in matches:
            self.memory.save_memory(f"proj_{m.replace('/', '_')}", m, "project")

        # Teknik detaylar
        tech_patterns = [
            (r"(?:kullanıyorum|kullanırım)\s+(python|javascript|rust|go|typescript|react|vue|docker|kubernetes)", "tech"),
            (r"(?:OS|işletim\s+sistemi)[\s:]*(\w+)", "environment"),
        ]
        for pattern, category in tech_patterns:
            matches = re.findall(pattern, user_message, re.IGNORECASE)
            for m in matches:
                self.memory.save_memory(f"{category}_{m.lower()}", m, category)
