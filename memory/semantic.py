"""Anlamsal bellek - ChromaDB ile vektör arama.

Kullanıcı hakkında öğrenilen bilgileri vektör olarak saklar.
"""

from __future__ import annotations
from typing import Optional

from core.logger import log


class SemanticMemory:
    """Vektör tabanlı anlamsal bellek. ChromaDB + FastEmbed ile."""

    def __init__(self, collection_name: str = "dorina_memory"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.embedder = None
        self._ready = False

    async def initialize(self):
        """ChromaDB ve embedder'ı başlat."""
        try:
            import chromadb
            from pathlib import Path as _P

            # Persistent local client — no server needed
            _db_path = str(_P(__file__).resolve().parent.parent / "data" / "chroma")
            try:
                self.client = chromadb.PersistentClient(path=_db_path)
            except Exception:
                self.client = chromadb.EphemeralClient()

            # Get or create collection
            try:
                self.collection = self.client.get_collection(self.collection_name)
            except Exception:
                self.collection = self.client.create_collection(self.collection_name)

            # FastEmbed
            try:
                from fastembed import TextEmbedding
                self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            except Exception as e:
                log.warning(f"FastEmbed yüklenemedi: {e}")
                self.embedder = None

            self._ready = True
            log.info(f"SemanticMemory hazir: {self.collection_name}")

        except Exception as e:
            log.warning(f"SemanticMemory başlatılamadı: {e}")
            self._ready = False

    def add(self, text: str, metadata: dict | None = None, doc_id: str | None = None):
        """Bilgi ekle — embedder varsa embedding ile, yoksa ChromaDB default."""
        if not self._ready or not self.collection:
            return

        import uuid
        doc_id = doc_id or str(uuid.uuid4())

        if self.embedder:
            # Use local embedder for consistent embeddings
            embedding = list(self.embedder.embed(text))[0]
            self.collection.add(
                embeddings=[list(embedding)],
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

    def search(self, query: str, n_results: int = 5) -> list[dict]:
        """Anlam benzerliğiyle ara — embedder varsa embedding ile."""
        if not self._ready or not self.collection:
            return []

        if self.embedder:
            query_emb = list(self.embedder.embed(query))[0]
            results = self.collection.query(
                query_embeddings=[list(query_emb)],
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

    def delete(self, doc_id: str):
        if self._ready and self.collection:
            self.collection.delete(ids=[doc_id])

    def count(self) -> int:
        if self._ready and self.collection:
            return self.collection.count()
        return 0

    def clear(self):
        """Tüm koleksiyonu temizle (sil ve yeniden oluştur)."""
        if self._ready and self.client:
            try:
                self.client.delete_collection(self.collection_name)
            except Exception:
                pass
            self.collection = self.client.create_collection(self.collection_name)
