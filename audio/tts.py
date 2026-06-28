"""
Text-to-Speech — edge-tts ile konuşma sentezi.

Async-first pattern:
    tts = AudioTTS()
    path = await tts.speak("Merhaba dünya", lang="tr")
"""

from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Optional
from core.logger import log


# ── Dil haritası (edge-tts sesleri) ─────────────────────────

VOICE_MAP = {
    "tr": "tr-TR-EmelNeural",
    "tr-female": "tr-TR-EmelNeural",
    "tr-male": "tr-TR-AhmetNeural",
    "en": "en-US-JennyNeural",
    "en-female": "en-US-JennyNeural",
    "en-male": "en-US-GuyNeural",
    "en-uk": "en-GB-SoniaNeural",
    "de": "de-DE-KatjaNeural",
    "fr": "fr-FR-DeniseNeural",
    "es": "es-ES-AlvaroNeural",
    "it": "it-IT-IsabellaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ja": "ja-JP-NanamiNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ar": "ar-SA-ZariyahNeural",
}


class AudioTTS:
    """
    edge-tts ile metin→ses dönüşümü.
    Async pattern: asyncio üzerinden çalışır, loop'u bloklamaz.
    """

    def __init__(self, output_dir: str = "/tmp/dorina_tts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.available = False
        self._check_available()

    def _check_available(self):
        """edge-tts modülü mevcut mu?"""
        try:
            import edge_tts  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    def _resolve_voice(self, lang: str) -> str:
        """Dil kodundan uygun sesi bul."""
        if lang in VOICE_MAP:
            return VOICE_MAP[lang]
        # Kısmi eşleşme: "tr-TR" -> "tr"
        lang_short = lang.split("-")[0] if "-" in lang else lang
        if lang_short in VOICE_MAP:
            return VOICE_MAP[lang_short]
        # Varsayılan İngilizce
        log.warning(f"Bilinmeyen dil '{lang}', varsayilan 'en' kullaniliyor")
        return VOICE_MAP["en"]

    async def speak(self, text: str, lang: str = "tr", voice: Optional[str] = None,
                    rate: int = 0, volume: int = 0, pitch: int = 0) -> str:
        """
        Metni sese çevir ve MP3 dosyasına kaydet.

        Args:
            text: Konuşulacak metin
            lang: Dil kodu (tr, en, de, fr, ...)
            voice: Doğrudan edge-tts ses adı (örn. \"tr-TR-EmelNeural\")
            rate: Hız ayarı (+-50 arası, 0=normal)
            volume: Ses seviyesi (+-50 arası, 0=normal)
            pitch: Perde ayarı

        Returns:
            MP3 dosya yolu, hata durumunda hata mesajı
        """
        if not self.available:
            return "TTS kullanilamiyor: edge-tts kurulu degil (pip install edge-tts)"

        if not text or not text.strip():
            return "TTS: Metin bos"

        try:
            import edge_tts
            voice_name = voice or self._resolve_voice(lang)

            # Dosya adı: text hash + zaman damgası
            safe_name = str(abs(hash(text + voice_name)))[:10]
            out_path = self.output_dir / f"tts_{safe_name}.mp3"

            communicate = edge_tts.Communicate(
                text,
                voice_name,
                rate=f"{rate:+d}%" if rate else None,
                volume=f"{volume:+d}%" if volume else None,
                pitch=f"{pitch:+d}Hz" if pitch else None,
            )
            await communicate.save(str(out_path))

            if out_path.exists():
                size_kb = out_path.stat().st_size / 1024
                log.info(f"TTS: {out_path} ({size_kb:.1f} KB) — {voice_name}")
                return str(out_path)
            else:
                return f"TTS: Dosya olusturulamadi: {out_path}"

        except Exception as e:
            log.error(f"TTS hatasi: {e}")
            return f"TTS basarisiz: {e}"

    async def speak_to_speaker(self, text: str, lang: str = "tr",
                                voice: Optional[str] = None) -> str:
        """
        Metni sese çevir ve hoparlörden çal (opsiyonel).
        pygame veya playsound gerektirir.
        """
        path = await self.speak(text, lang=lang, voice=voice)
        if path.startswith("TTS"):
            return path

        try:
            # Önce pygame, sonra playsound dene
            try:
                import pygame
                pygame.mixer.init()
                pygame.mixer.music.load(path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    await asyncio.sleep(0.1)
                pygame.mixer.quit()
            except ImportError:
                from playsound import playsound  # type: ignore
                await asyncio.to_thread(playsound, path)
            return f"Ses calindi: {path}"
        except Exception as e:
            return f"Ses calinamadi: {e}"

    def list_voices(self) -> list[dict]:
        """Kullanılabilir dilleri ve sesleri listele."""
        from edge_tts import list_voices  # type: ignore
        try:
            voices = asyncio.run(list_voices())
            return [
                {"name": v["ShortName"], "locale": v["Locale"], "gender": v["Gender"]}
                for v in voices
            ]
        except Exception as e:
            log.error(f"Ses listesi alinamadi: {e}")
            return []


# Singleton
tts_engine = AudioTTS()
