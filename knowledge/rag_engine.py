"""RAG motoru — ChromaDB ile belge sorgulama ve research entegrasyonu."""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from core.logger import log
from core.constants import DORINA_HOME


class RAGEngine:
    """Retrieval-Augmented Generation. Belgeleri vektörleştir, sorgula, research sonuçlarını ekle.

    Entegrasyon:
      - deep_research.py'den gelen raporları ve bulguları ekleyebilir
      - Her research sonucu metadata ile işaretlenir (source="deep_research")
    """

    def __init__(self):
        self.client = None
        self.collection = None
        self.embedder = None
        self._ready = False

    async def initialize(self):
        """ChromaDB bağlantısını başlat."""
        try:
            import chromadb
            try:
                self.client = chromadb.PersistentClient(
                    path=str(DORINA_HOME / "data" / "rag_knowledge"),
                )
            except Exception:
                return  # ChromaDB basarisiz, sessizce gec

            try:
                self.collection = self.client.get_collection("dorina_knowledge")
            except Exception:
                self.collection = self.client.create_collection("dorina_knowledge")

            try:
                from fastembed import TextEmbedding
                self.embedder = TextEmbedding()
            except Exception:
                pass

            self._ready = True
            log.info("RAGEngine hazır")
        except Exception as e:
            log.warning(f"RAGEngine başlatılamadı: {e}")

    def add_document(self, text: str, metadata: dict | None = None, doc_id: str | None = None):
        """Belge ekle."""
        if not self._ready:
            return
        import uuid
        doc_id = doc_id or str(uuid.uuid4())
        self.collection.add(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[doc_id],
        )

    def add_file(self, filepath: str):
        """Dosya ekle (PDF, TXT, MD)."""
        path = Path(filepath)
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8", errors="ignore")
        self.add_document(
            text=text,
            metadata={"source": str(path), "type": path.suffix},
        )

    # ── Deep Research Integration ────────────────────────────────

    def add_research_finding(self, query: str, finding_text: str, metadata: dict | None = None):
        """Araştırma bulgusunu vektör deposuna ekle.

        Args:
            query: Orijinal araştırma sorusu
            finding_text: Bulgu metni (rapor, snippet, makale)
            metadata: Ek metadata (kaynak URL, tarih, etc.)
        """
        meta = {
            "source": "deep_research",
            "query": query,
            "type": "research_finding",
        }
        if metadata:
            meta.update(metadata)
        self.add_document(text=finding_text, metadata=meta)

    def add_research_report(self, question: str, report: str, stats: dict | None = None):
        """Tam araştırma raporunu vektör deposuna ekle.

        Rapor chunk'lara bölünerek eklenir, böylece sonraki sorgularda
        raporun ilgili kısımları bulunabilir.

        Args:
            question: Araştırma sorusu
            report: Tam rapor metni
            stats: Araştırma istatistikleri (opsiyonel)
        """
        meta = {
            "source": "deep_research",
            "query": question,
            "type": "research_report",
        }
        if stats:
            meta["stats"] = str(stats)

        # Chunk the report into ~500 char segments
        chunk_size = 500
        chunks = [report[i:i + chunk_size] for i in range(0, len(report), chunk_size)]
        for i, chunk in enumerate(chunks):
            chunk_meta = {**meta, "chunk": i, "total_chunks": len(chunks)}
            self.add_document(text=chunk, metadata=chunk_meta)

    # ── Query ────────────────────────────────────────────────────

    def query(self, question: str, n_results: int = 3, filter_source: str | None = None) -> list[dict]:
        """Soru sor, ilgili belgeleri bul.

        Args:
            question: Sorgulanacak soru
            n_results: Döndürülecek maksimum sonuç sayısı
            filter_source: Sadece belirli kaynaktan sonuçlar (ör: "deep_research")

        Returns:
            {"content", "metadata", "distance"} sözlük listesi
        """
        if not self._ready:
            return []

        where = None
        if filter_source:
            where = {"source": filter_source}

        results = self.collection.query(
            query_texts=[question],
            n_results=n_results,
            where=where,
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

    def query_research(self, question: str, n_results: int = 3) -> list[dict]:
        """Sadece research sonuçlarından sorgula."""
        return self.query(question, n_results=n_results, filter_source="deep_research")

    def context_for_query(self, question: str, max_chars: int = 2000, include_research: bool = True) -> str:
        """Soru için bağlam oluştur (LLM'e eklemek için).

        Args:
            question: Sorgulanacak soru
            max_chars: Maksimum karakter sayısı
            include_research: Research sonuçlarını dahil et

        Returns:
            Biçimlendirilmiş bağlam metni
        """
        docs = self.query(question)
        if not docs:
            return ""

        context = "İlgili bilgiler:\n\n"
        total = 0
        for doc in docs:
            snippet = doc["content"][:500]
            if total + len(snippet) > max_chars:
                break
            source_label = doc.get("metadata", {}).get("source", "bilinmeyen")
            context += f"[{source_label}] {snippet}\n\n"
            total += len(snippet)

        return context

    def count(self) -> int:
        if self._ready:
            return self.collection.count()
        return 0


rag = RAGEngine()
