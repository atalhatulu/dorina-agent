"""Deep Research Pipeline — multi-step research with query analysis, parallel search, cross-referencing, and report generation.

Pipeline:
  Query Analysis → Sub-query Division → Parallel Search → Cross-reference → Report
"""

from __future__ import annotations
import asyncio
import json
import re
import time
from datetime import datetime
from typing import Any, Optional

from core.logger import log
from core.constants import t
from knowledge.web_search import web_search
from knowledge.web_scrape import scraper

# Shared ReasoningEngine — DeepResearcher creates its own instances otherwise
_research_engine: "ReasoningEngine | None" = None

def _get_research_engine():
    global _research_engine
    if _research_engine is None:
        from orchestrator.reasoning import ReasoningEngine
        _research_engine = ReasoningEngine()
    return _research_engine


def _now() -> str:
    return datetime.now().strftime("%B %d, %Y")


# ── Prompt Templates (extracted to research_prompts.py) ──────────
from knowledge.research_prompts import (
    QUERY_ANALYSIS_PROMPT,
    PARALLEL_SEARCH_PROMPT,
    CROSS_REFERENCE_PROMPT,
    SYNTHESIS_PROMPT,
    FINAL_REPORT_PROMPT,
)


class DeepResearcher:
    """Multi-step derin araştırma motoru.

    Pipeline:
      1. Query Analysis — sorguyu analiz et, alt-sorgulara böl
      2. Parallel Search — her alt-sorgu için paralel arama yap
      3. Cross Reference — bulguları çapraz referansla
      4. Synthesis — sentezle
      5. Final Report — nihai raporu oluştur
    """

    def __init__(self, llm_callback=None):
        self.llm = llm_callback
        self.findings: list[dict] = []
        self.start_time = 0.0
        self.max_time = 300  # 5 dk max
        self.max_iterations = 5
        self.iteration = 0
        self.cancelled = False
        self.stats = {
            "queries": 0,
            "pages_fetched": 0,
            "sub_questions": 0,
            "parallel_batches": 0,
            "errors": 0,
        }

    def cancel(self):
        self.cancelled = True

    async def research(self, question: str) -> str:
        """Ana araştırma pipeline'ı."""
        self.start_time = time.time()
        self.iteration = 0
        self.findings = []
        self.cancelled = False
        self.stats = {"queries": 0, "pages_fetched": 0, "sub_questions": 0, "parallel_batches": 0, "errors": 0}

        log.info(t("info_searching", query=question))

        # ── Step 1: Query Analysis ──────────────────────────────
        log.info("[Research] Step 1: Analyzing query...")
        analysis = await self._call_llm(QUERY_ANALYSIS_PROMPT.format(question=question))
        parsed = self._parse_json(analysis) or {}
        sub_questions = parsed.get("sub_questions", [question])
        search_queries = parsed.get("search_queries", [question])
        self.stats["sub_questions"] = len(sub_questions)
        log.info(f"[Research] {len(sub_questions)} alt-sorgu, {len(search_queries)} arama sorgusu")

        # ── Step 2: Parallel Search Pipeline ────────────────────
        log.info("[Research] Step 2: Running parallel searches...")

        # Batch 1: Search with generated queries
        batch_results = await self._parallel_search(search_queries, max_results=4)
        self.findings.extend(batch_results)
        self.stats["parallel_batches"] += 1

        # Batch 2: For each sub-question, generate more specific queries
        for sq in sub_questions[:3]:  # Limit to 3 sub-questions
            if self.cancelled or self._time_exceeded():
                break
            queries_text = await self._call_llm(
                PARALLEL_SEARCH_PROMPT.format(count=3, sub_question=sq)
            )
            more_queries = self._parse_json_array(queries_text) or [sq]
            more_results = await self._parallel_search(more_queries, max_results=3)
            self.findings.extend(more_results)
            self.stats["parallel_batches"] += 1

        log.info(f"... {len(self.findings)} findings collected")

        # ── Step 3: Cross Reference ─────────────────────────────
        log.info("[Research] Step 3: Cross-referencing...")
        findings_text = self._format_findings(self.findings)
        cross_ref_text = await self._call_llm(
            CROSS_REFERENCE_PROMPT.format(question=question, findings=findings_text)
        )
        cross_ref = self._parse_json(cross_ref_text) or {"common_themes": [], "contradictions": [], "gaps": []}
        log.info(f"[Research] Ortak tema: {len(cross_ref.get('common_themes', []))}, "
                 f"Çelişki: {len(cross_ref.get('contradictions', []))}, "
                 f"Boşluk: {len(cross_ref.get('gaps', []))}")

        # ── Step 4: Synthesis ───────────────────────────────────
        log.info("[Research] Step 4: Synthesizing results...")
        synthesis = await self._call_llm(
            SYNTHESIS_PROMPT.format(
                question=question,
                cross_ref=cross_ref_text,
                findings=findings_text,
            )
        )

        # ── Step 5: Iterative Deepening ─────────────────────────
        for iteration in range(self.max_iterations):
            if self.cancelled or self._time_exceeded():
                break
            self.iteration = iteration + 1

            # Check for gaps — decide if we need more research
            gaps = cross_ref.get("gaps", [])
            confidence = cross_ref.get("confidence_score", 0.5)

            if confidence >= 0.8 or not gaps or self.iteration >= self.max_iterations:
                break

            log.info(f"[Research] Iterasyon {self.iteration}: {len(gaps)} filling gaps...")
            gap_queries = gaps[:3]
            gap_results = await self._parallel_search(gap_queries, max_results=3)
            self.findings.extend(gap_results)
            self.stats["parallel_batches"] += 1

            # Re-cross-reference with new findings
            findings_text = self._format_findings(self.findings)
            cross_ref_text = await self._call_llm(
                CROSS_REFERENCE_PROMPT.format(question=question, findings=findings_text)
            )
            cross_ref = self._parse_json(cross_ref_text) or cross_ref

            # Re-synthesize
            synthesis = await self._call_llm(
                SYNTHESIS_PROMPT.format(
                    question=question,
                    cross_ref=cross_ref_text,
                    findings=findings_text,
                )
            )

        # ── Step 6: Final Report ───────────────────────────────
        log.info("[Research] Step 5: Generating final report...")
        final = await self._call_llm(
            FINAL_REPORT_PROMPT.format(question=question, synthesis=synthesis)
        )

        log.info(f"[Research] Tamam: {len(self.findings)} bulgu, "
                 f"{self.iteration} iterasyon, "
                 f"{self.stats['parallel_batches']} paralel batch")
        return self._clean_report(final)

    # ── Parallel Search ──────────────────────────────────────────

    async def _parallel_search(self, queries: list[str], max_results: int = 3) -> list[dict]:
        """Run multiple search queries and collect results."""
        results = []
        for query in queries:
            if self.cancelled:
                break
            self.stats["queries"] += 1
            try:
                search_results = await asyncio.to_thread(web_search.search_web, query, max_results=max_results)
                for r in search_results:
                    url = r.get("url", "") or r.get("href", "")
                    snippet = r.get("snippet", "") or r.get("body", "")
                    title = r.get("title", "")

                    page_text = None
                    if url:
                        try:
                            page_text = await asyncio.to_thread(scraper.fetch_sync, url)
                            self.stats["pages_fetched"] += 1
                        except (TimeoutError, ConnectionError, OSError):
                            pass

                    results.append({
                        "source": url,
                        "title": title,
                        "snippet": snippet,
                        "content": (page_text or snippet)[:2000],
                        "query": query,
                    })
                await asyncio.sleep(0.2)
            except (TimeoutError, OSError, ConnectionError, ValueError) as e:
                self.stats["errors"] += 1
                log.warning(f"Search error for '{query}': {e}")
        return results

    # ── LLM Call ─────────────────────────────────────────────────

    async def _call_llm(self, prompt: str) -> str:
        try:
            if self.llm:
                result = self.llm(prompt)
                if isinstance(result, dict):
                    return result.get("content", "")
                return str(result)
            else:
                engine = _get_research_engine()
                result = await engine.think(
                    system_prompt="You are a research assistant. Return concise, structured responses.",
                    messages=[{"role": "user", "content": prompt}],
                )
                content = result.get("content", "")
                # Clean JSON blocks
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                return content
        except (TimeoutError, OSError, KeyError, ImportError) as e:
            self.stats["errors"] += 1
            log.error(f"LLM error (research): {e}")
            return ""

    # ── Formatting Helpers ───────────────────────────────────────

    def _format_findings(self, findings: list[dict]) -> str:
        lines = []
        for i, f in enumerate(findings, 1):
            lines.append(f"[Finding {i}]")
            lines.append(f"Source: {f.get('source', 'N/A')}")
            lines.append(f"Title: {f.get('title', 'N/A')}")
            lines.append(f"Content: {(f.get('content', '') or '')[:500]}")
            lines.append("---")
        return "\n".join(lines)

    def _parse_json(self, text: str) -> dict | None:
        """Extract JSON object from text."""
        if not text:
            return None
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return None

    def _parse_json_array(self, text: str) -> list[str] | None:
        """Extract JSON array from text."""
        if not text:
            return None
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except (json.JSONDecodeError, TypeError):
                pass
        lines = []
        for l in text.split("\n"):
            line = l.strip()
            if line and not line.startswith(("#", "//")):
                # Eğer markdown listesi ise başındaki '- ' veya '* ' işaretini temizle
                import re as _re
                line = _re.sub(r'^[-*]\s+', '', line).strip('"\'')
                if line:
                    lines.append(line)
        return lines[:5] if lines else None

    def _clean_report(self, text: str) -> str:
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        text = re.sub(r'```[\w]*\n', '', text)
        text = re.sub(r'```', '', text)
        return text.strip()

    def _time_exceeded(self) -> bool:
        return (time.time() - self.start_time) > self.max_time

    def get_stats(self) -> dict:
        return {
            **self.stats,
            "findings": len(self.findings),
            "iterations": self.iteration,
            "elapsed": round(time.time() - self.start_time, 1),
        }


deep_researcher = DeepResearcher()
