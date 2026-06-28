"""
Speech-to-Text — whisper ile ses→metin dönüşümü.

Async-first pattern:
    stt = AudioSTT()
    text = await stt.transcribe("/tmp/kayit.wav")
"""

from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Optional
from core.logger import log


# ── Desteklenen formatlar ────────────────────────────────────

SUPPORTED_FORMATS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".webm"}


class AudioSTT:
    """
    OpenAI Whisper ile ses→metin dönüşümü.
    Async pattern: asyncio.to_thread ile bloklamaz.
    """

    def __init__(self, model_name: str = "base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None
        self.available = False
        self._check_available()

    def _check_available(self):
        """whisper modülü mevcut mu?"""
        try:
            import whisper  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    def _load_model(self):
        """Modeli lazy-load et."""
        if self._model is None and self.available:
            import whisper
            log.info(f"Whisper model yukleniyor: {self.model_name} ({self.device})")
            self._model = whisper.load_model(self.model_name, device=self.device)

    async def transcribe(self, audio_path: str, language: Optional[str] = None,
                         task: str = "transcribe", **kwargs) -> str:
        """
        Ses dosyasını metne çevir.

        Args:
            audio_path: Ses dosyası yolu (.wav, .mp3, .m4a, .ogg)
            language: Dil kodu (örn. \"tr\", \"en\"), None=oto-tespit
            task: \"transcribe\" veya \"translate\"
            **kwargs: Whisper.transcribe()'a ek parametreler

        Returns:
            Transkripsiyon metni veya hata mesajı
        """
        if not self.available:
            return "STT kullanilamiyor: whisper kurulu degil (pip install openai-whisper)"

        path = Path(audio_path).expanduser()
        if not path.exists():
            return f"STT: Dosya bulunamadi: {audio_path}"

        if path.suffix.lower() not in SUPPORTED_FORMATS:
            return f"STT: Desteklenmeyen format: {path.suffix} (desteklenen: {', '.join(SUPPORTED_FORMATS)})"

        try:
            # Model'i lazy-load (arka planda)
            self._load_model()
            if self._model is None:
                return "STT: Model yuklenemedi"

            # Transkripsiyon (async thread'de çalıştır)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(
                    str(path),
                    language=language,
                    task=task,
                    **kwargs
                )
            )

            text = result.get("text", "").strip()
            lang_detected = result.get("language", "?")
            duration = result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0

            log.info(f"STT: {path.name} -> {len(text)} karakter (dil={lang_detected}, sure={duration:.1f}s)")
            return text

        except Exception as e:
            log.error(f"STT hatasi: {e}")
            return f"STT basarisiz: {e}"

    async def transcribe_file(self, audio_path: str, language: Optional[str] = None) -> dict:
        """
        Ses dosyasını metne çevir ve detaylı sonuç döndür.

        Returns:
            dict: text, language, segments, duration bilgileri
        """
        if not self.available:
            return {"error": "STT kullanilamiyor"}

        path = Path(audio_path).expanduser()
        if not path.exists():
            return {"error": f"Dosya bulunamadi: {audio_path}"}

        try:
            self._load_model()
            if self._model is None:
                return {"error": "Model yuklenemedi"}

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: self._model.transcribe(
                    str(path),
                    language=language,
                    return_timestamps=True,
                )
            )

            return {
                "text": result.get("text", "").strip(),
                "language": result.get("language", "?"),
                "segments": [
                    {
                        "start": s.get("start", 0),
                        "end": s.get("end", 0),
                        "text": s.get("text", "").strip(),
                    }
                    for s in result.get("segments", [])
                ],
                "duration": result.get("segments", [{}])[-1].get("end", 0) if result.get("segments") else 0,
            }

        except Exception as e:
            log.error(f"STT detay hatasi: {e}")
            return {"error": str(e)}

    @property
    def model_info(self) -> dict:
        """Model hakkında bilgi."""
        return {
            "model": self.model_name,
            "device": self.device,
            "loaded": self._model is not None,
            "available": self.available,
        }


# Singleton
stt_engine = AudioSTT()
