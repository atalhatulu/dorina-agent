"""RAG motoru — SemanticMemory wrapper for knowledge retrieval.

Artik SemanticMemory uzerine insa edilmistir, ChromaDB kodunu tekrar etmez.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from core.logger import log
from memory.semantic import SemanticMemory


class RAGEngine:
    """Retrieval-Augmented Generation — SemanticMemory wrapper with knowledge-specific defaults.

    Backward-compatible: same public API, but storage layer is SemanticMemory.
    """

    def __init__(self):
        self._memory = SemanticMemory(
            collection_name="dorina_knowledge",
            db_path="rag_knowledge",
            embedding_model="BAAI/bge-small-en-v1.5",
        )
        self._ready = False

    @property
    def client(self):
        return self._memory.client

    @property
    def collection(self):
        return self._memory.collection

    @property
    def embedder(self):
        return self._memory.embedder

    async def initialize(self):
        """SemanticMemory'i baslat."""
        await self._memory.initialize()
        self._ready = self._memory._ready
        if self._ready:
            log.info("RAGEngine hazir (SemanticMemory tabanli)")
        else:
            log.warning("RAGEngine baslatilamadi")

    def add_document(self, text: str, metadata: dict | None = None, doc_id: str | None = None):
        """Belge ekle."""
        self._memory.add(text=text, metadata=metadata, doc_id=doc_id)

    def add(self, text: str, metadata: dict | None = None):
        """Short-hand for add_document (test compatibility)."""
        self._memory.add(text=text, metadata=metadata)

    def add_file(self, filepath: str):
        """Dosya ekle (PDF, TXT, MD)."""
        self._memory.add_file(filepath)

    def add_research_finding(self, query: str, finding_text: str, metadata: dict | None = None):
        """Araştırma bulgusunu ekle."""
        self._memory.add_research_finding(query, finding_text, metadata)

    def add_research_report(self, question: str, report: str, stats: dict | None = None):
        """Tam araştırma raporunu ekle."""
        self._memory.add_research_report(question, report, stats)

    def query(self, question: str, n_results: int = 3, filter_source: str | None = None) -> list[dict]:
        """Soru sor, ilgili belgeleri bul."""
        return self._memory.query(question, n_results=n_results, filter_source=filter_source)

    def search(self, question: str, n_results: int = 3) -> list[dict]:
        """Alias for query (test compatibility)."""
        return self._memory.search(question, n_results=n_results)

    def query_research(self, question: str, n_results: int = 3) -> list[dict]:
        """Sadece research sonuçlarından sorgula."""
        return self._memory.query_research(question, n_results=n_results)

    def context_for_query(self, question: str, max_chars: int = 2000, include_research: bool = True) -> str:
        """Soru için bağlam oluştur (LLM'e eklemek için)."""
        return self._memory.context_for_query(question, max_chars=max_chars)

    def count(self) -> int:
        if self._ready:
            return self._memory.count()
        return 0


rag = RAGEngine()
