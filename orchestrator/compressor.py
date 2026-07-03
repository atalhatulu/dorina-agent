"""
Context Compression — 2-tier semantic-aware context management.

Strategy:
  Tier 1 (fast path — default):
    - Remove oldest user/assistant/tool triples until under threshold
    - Keep system prompt + latest N turns
    - O(1) latency, zero token cost, no LLM call

  Tier 2 (LLM summarization — fallback):
    - Only when turn count > MAX_TURNS * 0.8 (~40 turns)
    - Or explicit /compress command
    - Calls LLM to summarize old turns into a condensed system message

Based on Hermes Agent's context_compactor.py pattern.
"""

from __future__ import annotations
import json
import re
from core.logger import log
from core.tokenizer import count_tokens, count_messages_tokens

COMPRESSION_THRESHOLD = 0.50  # Start compression at 50% capacity
KEEP_LATEST_TURNS = 4         # Latest turns preserved in Tier 1 truncation
SUMMARY_MAX_CHARS = 1500      # Summary maximum length
TIER2_TURN_THRESHOLD = 30     # Minimum turns before triggering Tier 2


class ContextCompressor:
    """
    Semantic-aware context compression.
    Preserves conversation triples (user-assistant-tool) rather than individual messages.
    """

    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.compression_count = 0
        self._previous_summaries: list[str] = []  # Accumulated summaries
        self._last_turns_len = 0                   # Previous compress_fast turn count

    def estimate_tokens(self, messages: list[dict]) -> int:
        return count_messages_tokens(messages)

    def _split_into_turns(self, messages: list[dict]) -> list[list[dict]]:
        """Split messages into user-assistant-tool triples (natural conversation turns).

        Each turn: chain of [user → assistant(tool_calls) → tool* → assistant].
        System messages are prepended as a separate turn.
        """
        if not messages:
            return []
        
        turns = []
        current: list[dict] = []
        
        for m in messages:
            role = m.get("role", "")
            
            if role == "system":
                # System message always stands alone
                if current:
                    turns.append(current)
                turns.append([m])
                current = []
                continue
            
            if role == "user":
                # New user message = new turn
                if current:
                    turns.append(current)
                current = [m]
            elif role == "assistant":
                current.append(m)
                # If tool_calls present, continue (tool results will follow)
                if not m.get("tool_calls"):
                    # No tool_calls = turn is complete
                    if current:
                        # If current only contains assistant (no preceding user),
                        # that's a bug — turns should start with user
                        pass
            elif role == "tool":
                current.append(m)
                # Tool sonrasi assistant mesaji ayni turda olabilir
            else:
                # Unknown roles (function, etc.) — include to avoid data loss
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

    async def compress(
        self,
        messages: list[dict],
        llm_callback=None,
        force_tier2: bool = False,
        turn_count: int = 0,
    ) -> list[dict]:
        """Auto-select Tier 1 (fast truncation) or Tier 2 (LLM summarization).

        Args:
            messages: Current message list.
            llm_callback: Async callable for LLM summarization (required for Tier 2).
            force_tier2: If True, always use LLM summarization (e.g. /compress).
            turn_count: Current turn count — used to decide when to upgrade to Tier 2.

        Returns:
            Compressed message list.
        """
        if len(messages) < 6:
            return messages

        use_tier2 = force_tier2 or (turn_count >= TIER2_TURN_THRESHOLD and llm_callback is not None)

        if use_tier2:
            return await self._compress_llm(messages, llm_callback)
        return self._compress_fast(messages)

    # ────────────────────────────────────────────────────────────────
    # TIER 1 — O(1) truncation (default, no LLM call)
    # ────────────────────────────────────────────────────────────────

    def _compress_fast(self, messages: list[dict]) -> list[dict]:
        """Fast path: remove oldest turns, keep system + latest KEEP_LATEST_TURNS."""
        turns = self._split_into_turns(messages)
        if len(turns) < 3:
            return messages

        # Keep the latest KEEP_LATEST_TURNS turns intact
        keep_count = min(KEEP_LATEST_TURNS, len(turns) - 1)
        keep_turns = turns[-keep_count:]
        compress_turns = turns[:-keep_count]

        # System messages remain protected (split_into_turns separates them)
        system_turns = [t for t in compress_turns if t[0].get("role") == "system"]
        if system_turns:
            # System message goes first
            result = system_turns + keep_turns
        else:
            result = keep_turns

        # Flatten
        flat = []
        for t in result:
            flat.extend(t)

        self._last_turns_len = len(turns)
        self.compression_count += 1
        log.info(
            f"Context compressed (Tier 1): {len(compress_turns)} old turns removed, "
            f"kept last {keep_count} ({len(messages)} msgs → {len(flat)} msgs)"
        )
        return flat

    # ────────────────────────────────────────────────────────────────
    # TIER 2 — LLM summarization (for long conversations)
    # ────────────────────────────────────────────────────────────────

    async def _compress_llm(self, messages: list[dict], llm_callback) -> list[dict]:
        """LLM-based compression: summarize old turns with a condensed system message."""
        self.compression_count += 1

        # If no LLM callback available, fall back to Tier 1 truncation
        if llm_callback is None:
            log.warning("No LLM callback for Tier 2, falling back to Tier 1")
            return self._compress_fast(messages)

        turns = self._split_into_turns(messages)
        if len(turns) < 2:
            return messages

        if len(turns) <= KEEP_LATEST_TURNS + 1:
            keep_count = max(1, len(turns) - 1)
        else:
            keep_count = KEEP_LATEST_TURNS

        keep_turns = turns[-keep_count:]
        compress_turns = turns[:-keep_count]

        # Convert turns to plain text for summarization
        exchange_text = self._format_turns(compress_turns)

        # Try LLM summarization
        summary = ""
        try:
            summary = await llm_callback(
                f"Summarize this conversation exchange concisely. "
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

        # Fall back to truncation
        if not summary:
            fallback_text = self._format_turns(compress_turns)
            if len(fallback_text) > SUMMARY_MAX_CHARS:
                fallback_text = fallback_text[:SUMMARY_MAX_CHARS] + "\n[...]"
            summary = f"[Older conversation history truncated]\n{fallback_text[:SUMMARY_MAX_CHARS]}"

        # Accumulate summary
        self._previous_summaries.append(str(summary))
        if len(self._previous_summaries) > 3:
            self._previous_summaries = self._previous_summaries[-3:]

        # Previous summaries + new summary + kept turns
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

        keep_messages = []
        for t in keep_turns:
            keep_messages.extend(t)

        result = [compressed_msg] + keep_messages
        log.info(
            f"Context compressed (Tier 2): {len(compress_turns)} old turns → 1 summary "
            f"({len(messages)} msgs → {len(result)} msgs, "
            f"kept last {keep_count} turns)"
        )
        return result

    def _format_turns(self, turns: list[list[dict]]) -> str:
        """Convert turn list to plain text for summarization."""
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
        return "\n".join(lines[-50:])  # Max 50 lines

    def reset(self):
        self.compression_count = 0
        self._previous_summaries = []
