"""Anlamsal bellek - ChromaDB ile vektor arama.

Kullanici hakkinda ogrenilen bilgileri vektor olarak saklar.
"""

from __future__ import annotations
from typing import Any, Optional

from core.logger import log
from memory.base import BaseMemory


class SemanticMemory(BaseMemory):
    """Vektor tabanli anlamsal bellek. ChromaDB + FastEmbed ile."""

    memory_type = "semantic"

    def __init__(self, collection_name: str = "dorina_memory", db_path: str = "chroma", embedding_model: str = "BAAI/bge-small-en-v1.5"):
        self.collection_name = collection_name
        self.db_path = db_path
        self.embedding_model = embedding_model
        self.client = None
        self.collection = None
        self.embedder = None
        self._ready = False

    async def initialize(self):
        """ChromaDB ve embedder'i baslat."""
        try:
            import chromadb
            from core.constants import DORINA_HOME

            _db_path = str(DORINA_HOME / "data" / self.db_path)
            try:
                self.client = chromadb.PersistentClient(path=_db_path)
            except (ImportError, ValueError, OSError):
                self.client = chromadb.EphemeralClient()

            try:
                self.collection = self.client.get_collection(self.collection_name)
            except (ValueError, KeyError):
                self.collection = self.client.create_collection(self.collection_name)

            try:
                from fastembed import TextEmbedding
                self.embedder = TextEmbedding(model_name=self.embedding_model)
                # Force download to complete BEFORE prompt appears
                list(self.embedder.embed(["warmup"]))
            except (ImportError, OSError, ValueError, TypeError) as e:
                log.warning(f"FastEmbed yuklenemedi: {e}")
                self.embedder = None

            self._ready = True
            log.info(f"SemanticMemory hazir: {self.collection_name} ({self.db_path})")

        except (ImportError, ValueError, OSError) as e:
            log.warning(f"SemanticMemory baslatilamadi: {e}")
            self._ready = False

    def _to_float_list(self, embedding) -> list[float]:
        """np.float32 veya numpy array'i Python float listesine cevir."""
        import numpy as np
        if isinstance(embedding, np.ndarray):
            return embedding.tolist()
        if hasattr(embedding, '__iter__'):
            return [float(x) for x in embedding]
        return [float(embedding)]

    def get(self, doc_id: str) -> dict | None:
        """Get a document by ID.

        Args:
            doc_id: Document ID.

        Returns:
            Document dict with content and metadata, or None.
        """
        if not self._ready or not self.collection:
            return None
        try:
            results = self.collection.get(ids=[doc_id])
            if results and results.get("documents") and results["documents"][0]:
                return {
                    "content": results["documents"][0],
                    "metadata": (results["metadatas"][0] or {}) if results.get("metadatas") else {},
                    "id": doc_id,
                }
            return None
        except (ValueError, KeyError, OSError) as e:
            log.error(f"SemanticMemory.get hatasi: {e}")
            return None

    def add(self, text: str, metadata: dict | None = None, doc_id: str | None = None):
        if not self._ready or not self.collection:
            return
        import uuid
        doc_id = doc_id or str(uuid.uuid4())
        try:
            if self.embedder:
                emb = list(self.embedder.embed(text))[0]
                embedding = self._to_float_list(emb)
                self.collection.add(
                    embeddings=[embedding],
                    documents=[text],
                    metadatas=[metadata or {}],
                    ids=[doc_id],
                )
            else:
                self.collection.add(
                    documents=[text],
                    metadatas=[metadata or {}],
                    ids=[doc_id],
                )
        except (ValueError, KeyError, OSError) as e:
            log.error(f"SemanticMemory.add hatasi: {e}")

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        if not self._ready or not self.collection:
            return []
        try:
            if self.embedder:
                emb = list(self.embedder.embed(query))[0]
                query_emb = self._to_float_list(emb)
                results = self.collection.query(
                    query_embeddings=[query_emb],
                    n_results=n_results,
                )
            else:
                results = self.collection.query(
                    query_texts=[query],
                    n_results=n_results,
                )
            items = []
            if results and results.get("documents"):
                for i, doc in enumerate(results["documents"][0]):
                    items.append({
                        "content": doc,
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": results["distances"][0][i] if results.get("distances") else 0,
                    })
            return items
        except (ValueError, KeyError, OSError) as e:
            log.error(f"SemanticMemory.search hatasi: {e}")
            return []

    def delete(self, doc_id: str):
        if self._ready and self.collection:
            try:
                self.collection.delete(ids=[doc_id])
            except (ValueError, KeyError, OSError) as e:
                log.error(f"SemanticMemory.delete hatasi: {e}")

    def count(self) -> int:
        if self._ready and self.collection:
            try:
                return self.collection.count()
            except (ValueError, KeyError, OSError) as e:
                log.error(f"SemanticMemory.count hatasi: {e}")
        return 0

    def clear(self):
        if self._ready and self.client:
            try:
                self.client.delete_collection(self.collection_name)
            except ValueError:
                pass
            self.collection = self.client.create_collection(self.collection_name)

    # ── RAG/knowledge extensions ─────────────────────────────────

    def add_file(self, filepath: str):
        """Read file and add to vector store (PDF, TXT, MD)."""
        from pathlib import Path as _P
        path = _P(filepath)
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
        self.add(
            text=text,
            metadata={"source": str(path), "type": path.suffix},
        )

    def add_research_finding(self, query: str, finding_text: str, metadata: dict | None = None):
        """Add research finding to vector store."""
        meta = {
            "source": "deep_research",
            "query": query,
            "type": "research_finding",
        }
        if metadata:
            meta.update(metadata)
        self.add(text=finding_text, metadata=meta)

    def add_research_report(self, question: str, report: str, stats: dict | None = None):
        """Split full research report into chunks and add to store."""
        meta = {
            "source": "deep_research",
            "query": question,
            "type": "research_report",
        }
        if stats:
            meta["stats"] = str(stats)

        chunk_size = 500
        chunks = [report[i:i + chunk_size] for i in range(0, len(report), chunk_size)]
        for i, chunk in enumerate(chunks):
            chunk_meta = {**meta, "chunk": i, "total_chunks": len(chunks)}
            self.add(text=chunk, metadata=chunk_meta)

    def query(self, question: str, n_results: int = 3, filter_source: str | None = None) -> list[dict]:
        """Ask a question, find relevant documents (alias for search with optional source filter)."""
        if filter_source:
            # Post-filter by source metadata
            results = self.search(question, n_results=n_results * 3)
            return [r for r in results if r.get("metadata", {}).get("source") == filter_source][:n_results]
        return self.search(question, n_results=n_results)

    def query_research(self, question: str, n_results: int = 3) -> list[dict]:
        """Query only deep_research-sourced results."""
        return self.query(question, n_results=n_results, filter_source="deep_research")

    def context_for_query(self, question: str, max_chars: int = 2000) -> str:
        """Create formatted context text for a query (to add to LLM context)."""
        docs = self.search(question)
        if not docs:
            return ""

        context = "Relevant information:\n\n"
        total = 0
        for doc in docs:
            snippet = doc["content"][:500]
            if total + len(snippet) > max_chars:
                break
            source_label = doc.get("metadata", {}).get("source", "unknown")
            context += f"[{source_label}] {snippet}\n\n"
            total += len(snippet)

        return context
