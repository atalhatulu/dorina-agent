"""
Dorina Agent — Ses (TTS + STT) modülü.

İyileştirilmiş edge-tts ile konuşma sentezi + whisper STT.
Async first pattern: tüm TTS/STT işlemleri asyncio üzerinden.
"""

from __future__ import annotations
from audio.tts import AudioTTS, tts_engine
from audio.stt import AudioSTT, stt_engine
from audio.microphone import MicrophoneRecorder, mic

__all__ = ["AudioTTS", "tts_engine", "AudioSTT", "stt_engine", "MicrophoneRecorder", "mic"]
