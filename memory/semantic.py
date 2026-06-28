"""Anlamsal bellek - ChromaDB ile vektor arama.

Kullanici hakkinda ogrenilen bilgileri vektor olarak saklar.
"""

from __future__ import annotations
from typing import Optional

from core.logger import log


class SemanticMemory:
    """Vektor tabanli anlamsal bellek. ChromaDB + FastEmbed ile."""

    def __init__(self, collection_name: str = "dorina_memory"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embedder = None
        self._ready = False

    async def initialize(self):
        """ChromaDB ve embedder'i baslat."""
        try:
            import chromadb
            from pathlib import Path as _P
            from core.constants import DORINA_HOME

            _db_path = str(DORINA_HOME / "data" / "chroma")
            try:
                self.client = chromadb.PersistentClient(path=_db_path)
            except Exception:
                self.client = chromadb.EphemeralClient()

            try:
                self.collection = self.client.get_collection(self.collection_name)
            except Exception:
                self.collection = self.client.create_collection(self.collection_name)

            try:
                from fastembed import TextEmbedding
                self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            except Exception as e:
                log.warning(f"FastEmbed yuklenemedi: {e}")
                self.embedder = None

            self._ready = True
            log.info(f"SemanticMemory hazir: {self.collection_name}")

        except Exception as e:
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
        except Exception as e:
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
        except Exception as e:
            log.error(f"SemanticMemory.search hatasi: {e}")
            return []

    def delete(self, doc_id: str):
        if self._ready and self.collection:
            try:
                self.collection.delete(ids=[doc_id])
            except Exception as e:
                log.error(f"SemanticMemory.delete hatasi: {e}")

    def count(self) -> int:
        if self._ready and self.collection:
            try:
                return self.collection.count()
            except Exception as e:
                log.error(f"SemanticMemory.count hatasi: {e}")
        return 0

    def clear(self):
        if self._ready and self.client:
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass
            self.collection = self.client.create_collection(self.collection_name)
