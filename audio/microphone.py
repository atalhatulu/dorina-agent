"""
Mikrofon kaydedici — PyAudio ile ses kaydı.

Async-first pattern:
    mic = MicrophoneRecorder()
    path = await mic.record(duration=5)
"""

from __future__ import annotations
import asyncio
import os
import tempfile
import wave
from pathlib import Path
from typing import Optional, Callable
from core.logger import log


class MicrophoneRecorder:
    """
    PyAudio ile mikrofon ses kaydı.
    Async pattern: asyncio.to_thread ile bloklamaz.
    """

    def __init__(self, sample_rate: int = 16000, channels: int = 1,
                 chunk_size: int = 1024, output_dir: str = "/tmp/dorina_audio"):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.available = False
        self._check_available()

    def _check_available(self):
        """PyAudio mevcut mu?"""
        try:
            import pyaudio  # noqa: F401
            self.available = True
        except ImportError:
            self.available = False

    def _list_devices(self) -> list[dict]:
        """Ses cihazlarını listele."""
        if not self.available:
            return []
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            devices = []
            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0:
                    devices.append({
                        "index": i,
                        "name": info["name"],
                        "channels": info["maxInputChannels"],
                        "sample_rate": int(info["defaultSampleRate"]),
                    })
            p.terminate()
            return devices
        except Exception as e:
            log.error(f"Cihaz listesi hatasi: {e}")
            return []

    async def record(self, duration: int = 5, device_index: Optional[int] = None,
                     output_path: Optional[str] = None) -> str:
        """
        Mikrofondan ses kaydet.

        Args:
            duration: Kayıt süresi (saniye, varsayılan: 5)
            device_index: Ses cihazı indeksi (None=varsayılan)
            output_path: Çıktı dosyası yolu (None=otomatik)

        Returns:
            WAV dosya yolu veya hata mesajı
        """
        if not self.available:
            return "Mikrofon kullanilamiyor: pyaudio kurulu degil (pip install pyaudio)"

        try:
            import pyaudio

            # Çıktı dosyası
            if output_path:
                out_path = Path(output_path).expanduser()
            else:
                out_path = self.output_dir / f"recording_{abs(hash(str(duration))) % 10000:04d}.wav"
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Mikrofon kaydı (thread'de çalıştır)
            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(
                None,
                lambda: self._record_sync(
                    str(out_path), duration, device_index
                )
            )

            if success and out_path.exists():
                size_kb = out_path.stat().st_size / 1024
                log.info(f"Mikrofon: {out_path} ({duration}s, {size_kb:.1f} KB)")
                return str(out_path)
            else:
                return f"Mikrofon: Kayit basarisiz"

        except Exception as e:
            log.error(f"Mikrofon kayit hatasi: {e}")
            return f"Mikrofon hatasi: {e}"

    def _record_sync(self, output_path: str, duration: int, device_index: Optional[int]) -> bool:
        """Senkron mikrofon kaydı (thread için)."""
        try:
            import pyaudio
            import wave

            p = pyaudio.PyAudio()

            # Cihaz seçimi
            device_info = None
            if device_index is not None:
                device_info = p.get_device_info_by_index(device_index)
                sample_rate = int(device_info["defaultSampleRate"])
                channels = min(self.channels, int(device_info["maxInputChannels"]))
            else:
                sample_rate = self.sample_rate
                channels = self.channels

            stream = p.open(
                format=pyaudio.paInt16,
                channels=channels,
                rate=sample_rate,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=self.chunk_size,
            )

            frames = []
            total_frames = int(sample_rate / self.chunk_size * duration)
            for _ in range(total_frames):
                data = stream.read(self.chunk_size, exception_on_overflow=False)
                frames.append(data)

            stream.stop_stream()
            stream.close()
            p.terminate()

            # WAV yaz
            with wave.open(output_path, "wb") as wf:
                wf.setnchannels(channels)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(sample_rate)
                wf.writeframes(b"".join(frames))

            return True

        except Exception as e:
            log.error(f"Mikrofon record_sync hatasi: {e}")
            return False

    async def record_stream(self, duration: int = 5, chunk_callback: Optional[Callable] = None,
                            device_index: Optional[int] = None) -> str:
        """
        Stream modunda kaydet — her chunk için callback çağrılır.

        Args:
            duration: Kayıt süresi (saniye)
            chunk_callback: Her chunk sonrası çağrılacak fonksiyon (data: bytes)
            device_index: Ses cihazı indeksi

        Returns:
            WAV dosya yolu
        """
        return await self.record(duration=duration, device_index=device_index)

    def list_devices(self) -> str:
        """Kullanılabilir mikrofon cihazlarını listele (string)."""
        import json
        devices = self._list_devices()
        if not devices:
            if not self.available:
                return "pyaudio kurulu degil"
            return "Mikrofon cihazi bulunamadi"
        return json.dumps(devices, ensure_ascii=False)


# Singleton
mic = MicrophoneRecorder()
