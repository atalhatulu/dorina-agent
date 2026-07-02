"""
Context Compression — semantic-aware context management.

Hermes Agent'in context_compactor.py deseninden esinlenilmiştir.

Strateji:
1. Token limiti %50 dolunca sıkıştırmayı başlat
2. User-Asistan-Tool üçlülerini KORU (parçalama)
3. Eski turları özetle, yeni turları olduğu gibi tut
4. Özetleri biriktir (önceki özetleri de koru)
5. LLM çağrısı başarısız olursa fallback: en eski üçlüleri sil
"""

from __future__ import annotations
import json
import re
from core.logger import log
from core.tokenizer import count_tokens, count_messages_tokens

COMPRESSION_THRESHOLD = 0.50  # %50 dolulukta sıkıştırmayı başlat
KEEP_LATEST_TURNS = 2         # En az bu kadar son turu koru (dokunma)
SUMMARY_MAX_CHARS = 1500      # Özet maksimum uzunluk


class ContextCompressor:
    """
    Semantic-aware context compression.
    Preserves conversation triples (user-assistant-tool) rather than individual messages.
    """

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.compression_count = 0
        self._previous_summaries: list[str] = []  # Birikimli özetler

    def estimate_tokens(self, messages: list[dict]) -> int:
        return count_messages_tokens(messages)

    def _split_into_turns(self, messages: list[dict]) -> list[list[dict]]:
        """Mesajları user-asistan-tool üçlülerine ayır (natural conversation turns).
        
        Her tur: [user → assistant(tool_calls) → tool* → assistant] zinciridir.
        System mesajı ayrı bir tur olarak başa eklenir.
        """
        if not messages:
            return []
        
        turns = []
        current: list[dict] = []
        
        for m in messages:
            role = m.get("role", "")
            
            if role == "system":
                # System mesajı her zaman kendi başına
                if current:
                    turns.append(current)
                turns.append([m])
                current = []
                continue
            
            if role == "user":
                # Yeni user mesajı = yeni tur
                if current:
                    turns.append(current)
                current = [m]
            elif role == "assistant":
                current.append(m)
                # tool_calls varsa devam (tool sonuçları gelecek)
                if not m.get("tool_calls"):
                    # tool_calls yoksa tur bitti
                    if current:
                        # Eğer current sadece assistant'tan oluşuyorsa (önceki tur user'ı burada değil)
                        # bu bir hata, user ile başlamalı
                        pass
            elif role == "tool":
                current.append(m)
                # Tool sonrasi assistant mesaji ayni turda olabilir
            else:
                # Bilinmeyen roller (function, vs) veri kaybini onlemek icin ekle
                current.append(m)
        
        if current:
            turns.append(current)
        
        return turns

    def should_compress(self, messages: list[dict]) -> bool:
        if not messages:
            return False
        estimated = self.estimate_tokens(messages)
        ratio = estimated / self.max_tokens
        return ratio > COMPRESSION_THRESHOLD

    async def compress(self, messages: list[dict], llm_callback) -> list[dict]:
        """Compress context preserving full recent turns, summarizing old ones."""
        if len(messages) < 6:  # En az 2 user-asistan-tool üçlüsü
            return messages

        self.compression_count += 1

        # 1. Mesajları turlara ayır
        turns = self._split_into_turns(messages)
        if len(turns) < 2:
            return messages

        # 2. Son KEEP_LATEST_TURNS turu aynen koru
        if len(turns) <= KEEP_LATEST_TURNS + 1:
            keep_count = max(1, len(turns) - 1)
        else:
            keep_count = KEEP_LATEST_TURNS

        keep_turns = turns[-keep_count:]
        compress_turns = turns[:-keep_count]

        # 3. Sıkıştırılacak turları düz metne çevir
        exchange_text = self._format_turns(compress_turns)

        # 4. LLM ile özet çıkarmayı dene
        summary = ""
        try:
            summary = await llm_callback(
                f"Summarize this conversation exchange concisely in Turkish. "
                f"Extract: decisions, file contents, user preferences, technical setup, task status. "
                f"Keep important names, IPs, commands, and filenames.\n\n"
                f"Previous summaries:\n{chr(10).join(self._previous_summaries[-3:])}\n\n"
                f"New content to summarize:\n{exchange_text}"
            )
            if isinstance(summary, dict):
                summary = summary.get("content", "")[:SUMMARY_MAX_CHARS]
            else:
                summary = str(summary)[:SUMMARY_MAX_CHARS]
        except (TimeoutError, OSError, json.JSONDecodeError, KeyError) as e:
            log.warning(f"LLM compression failed ({e}), using truncation fallback")

        # 5. Fallback: özet çıkmazsa eski turların sadece ilk mesajını tut
        if not summary:
            fallback_text = self._format_turns(compress_turns)
            if len(fallback_text) > SUMMARY_MAX_CHARS:
                fallback_text = fallback_text[:SUMMARY_MAX_CHARS] + "\n[...]"
            summary = f"[Older conversation history truncated]\n{fallback_text[:SUMMARY_MAX_CHARS]}"

        # 6. Özeti biriktir
        self._previous_summaries.append(str(summary))
        if len(self._previous_summaries) > 3:
            self._previous_summaries = self._previous_summaries[-3:]

        # 7. Sonucu oluştur: önceki özetler + yeni özet + korunan turlar
        summaries_text = "\n".join(
            f"[Previous summary {i+1}]: {s[:300]}"
            for i, s in enumerate(self._previous_summaries[:-1])
        )

        compressed_msg = {
            "role": "system",
            "content": (
                f"[Conversation summary #{self.compression_count}]:\n"
                f"{summaries_text}\n"
                f"[Latest summary]: {summary}"
            ),
            "compressed": True,
        }

        # 8. Keep turns'leri düzleştir
        keep_messages = []
        for t in keep_turns:
            keep_messages.extend(t)

        result = [compressed_msg] + keep_messages
        log.info(
            f"Context compressed: {len(compress_turns)} old turns → 1 summary "
            f"({len(messages)} msgs → {len(result)} msgs, "
            f"kept last {keep_count} turns)"
        )
        return result

    def _format_turns(self, turns: list[list[dict]]) -> str:
        """Turn listesini özet için düz metne çevir."""
        lines = []
        for turn in turns:
            turn_text = []
            for m in turn:
                role = m.get("role", "?")
                content = str(m.get("content", ""))
                name = m.get("name", "")
                if role == "user":
                    turn_text.append(f"User: {content[:300]}")
                elif role == "assistant":
                    tc = m.get("tool_calls")
                    if tc:
                        tools = [t.get("function", {}).get("name", "?") for t in tc]
                        turn_text.append(f"Assistant [tools: {', '.join(tools)}]: {content[:200]}")
                    else:
                        turn_text.append(f"Assistant: {content[:400]}")
                elif role == "tool":
                    turn_text.append(f"  → Tool [{name}]: {str(content)[:150]}")
                elif role == "system":
                    turn_text.append(f"[System]: {content[:100]}")
            if turn_text:
                lines.extend(turn_text)
                lines.append("---")
        return "\n".join(lines[-50:])  # En fazla 50 satır

    def reset(self):
        self.compression_count = 0
        self._previous_summaries = []
