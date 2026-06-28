"""
Context Compression — semantic-aware context management.

Strateji:
1. Token limiti aşılma noktasına geldiğinde
2. Mesajları semantik önem skoruna göre sırala
3. Düşük önemli mesajları özetle, yüksek önemlileri koru
4. Özeti tek mesaj olarak ekle
5. Eski/korunmasız mesajları kaldır

Hermes Agent'in context_compactor.py deseninden esinlenilmiştir.
"""

from __future__ import annotations
import re
from typing import Optional
from core.logger import log
from core.tokenizer import count_tokens, count_messages_tokens

COMPRESSION_THRESHOLD = 0.75  # %75 dolulukta sıkıştırmayı düşün
TARGET_RATIO = 0.40  # Sıkıştırma sonrası hedef doluluk

# Semantic importance signals — satır içinde aranır
_HIGH_SIGNAL = re.compile(
    r"(karar|decision|seç|choose|prefer|tercih|şifre|password|token|api.key|"
    r"kur|install|config|ayar|setting|önemli|important|critical|"
    r"hatırla|remember|not et|note|kaydet|save|commit|deploy)",
    re.IGNORECASE,
)

COMPRESSION_PROMPT = """\
Summarize the key information from this conversation exchange 
that an AI assistant needs to remember for future context.
Include: decisions made, user preferences, technical details, task status.
Exclude: greetings, small talk, repetitive content.

Focus on actionable information. Be concise.

Conversation to summarize:
{messages}
"""


class ContextCompressor:
    """
    Semantic-aware context compression.
    Preserves high-importance messages while summarizing low-importance ones.
    """

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.compression_count = 0

    def estimate_tokens(self, messages: list[dict]) -> int:
        return count_messages_tokens(messages)

    def _score_message(self, msg: dict) -> int:
        """Semantic importance score (0-10). Higher = more important to keep."""
        role = msg.get("role", "")
        content = str(msg.get("content", ""))

        score = 0

        # Role-based base score
        if role == "system":
            score += 3
        elif role == "user":
            score += 1
        elif role == "assistant":
            score += 1

        # Length signal: very short messages are less important
        if len(content) > 200:
            score += 1
        if len(content) < 10:
            score -= 1

        # Semantic signals
        if _HIGH_SIGNAL.search(content):
            score += 5

        # Compressed messages already have lower priority
        if msg.get("compressed"):
            score -= 2

        return max(0, min(10, score))

    def should_compress(self, messages: list[dict]) -> bool:
        if not messages:
            return False
        estimated = self.estimate_tokens(messages)
        ratio = estimated / self.max_tokens
        return ratio > COMPRESSION_THRESHOLD

    async def compress(self, messages: list[dict], llm_callback) -> list[dict]:
        """Compress context preserving important messages."""
        if len(messages) < 4:
            return messages

        self.compression_count += 1

        # Score and sort: keep high-scoring messages, compress low-scoring ones
        scored = [(self._score_message(m), m) for m in messages]
        scored.sort(key=lambda x: (x[0], -messages.index(x[1])))

        # Keep top 30% by score (at least 2 messages)
        keep_count = max(2, len(messages) // 3)
        to_keep = [m for _, m in scored[-keep_count:]]

        # Reconstruct original order for kept messages
        seen_ids = set(id(m) for m in to_keep)
        to_keep_ordered = [m for m in messages if id(m) in seen_ids]

        # Compress the rest (low-scoring)
        to_compress = [m for m in messages if id(m) not in seen_ids]

        if not to_compress:
            # All messages are important — fall back to old-style oldest 50%
            compress_count = max(2, len(messages) // 2)
            to_compress = messages[:compress_count]
            to_keep_ordered = messages[compress_count:]

        exchange_text = self._format_exchange(to_compress)

        try:
            summary = await llm_callback(
                COMPRESSION_PROMPT.format(messages=exchange_text)
            )

            compressed_msg = {
                "role": "system",
                "content": f"[Compressed summary #{self.compression_count}]: {summary[:500]}",
                "compressed": True,
            }

            result = [compressed_msg] + to_keep_ordered
            log.info(f"Context sıkıştırıldı: {len(to_compress)} → 1 mesaj "
                     f"(toplam: {len(messages)} → {len(result)}, "
                     f"korunan: {len(to_keep_ordered)})")
            return result

        except Exception as e:
            log.warning(f"Context sıkıştırma hatası: {e}")
            return messages

    def _format_exchange(self, messages: list[dict]) -> str:
        lines = []
        for m in messages:
            role = m.get("role", "unknown")
            content = m.get("content", "")
            name = m.get("name", "")

            if role == "user":
                lines.append(f"User: {content[:200]}")
            elif role == "assistant":
                lines.append(f"Assistant: {content[:500]}")
            elif role == "tool":
                lines.append(f"Tool [{name}]: {str(content)[:200]}")

        return "\n".join(lines[-20:])

    def reset(self):
        self.compression_count = 0
