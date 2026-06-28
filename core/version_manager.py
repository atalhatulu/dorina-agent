"""
Version Manager — Proje sürümünü okur, artırır ve kaydeder.

Kullanım:
    from core.version_manager import VersionManager

    v = VersionManager()
    print(v.current)        # "0.1.0"
    v.bump_patch()          # "0.1.1"
    v.bump_minor()          # "0.2.0"
    v.bump_major()          # "1.0.0"

Dosyaya otomatik kaydeder (core/version.txt).
"""

from __future__ import annotations
import re
from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parent / "version.txt"
DEFAULT_VERSION = "0.1.0"

# ── Semver regex: major.minor.patch (ör: 1.2.3, 0.1.0-dev de kabul) ──
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(-.*)?$")


class VersionError(Exception):
    """Versiyon ile ilgili hatalar için."""


class VersionManager:
    """Proje sürümünü dosyadan okur, artırır ve geri yazar."""

    def __init__(self, filepath: str | Path | None = None):
        self._file = Path(filepath) if filepath else VERSION_FILE
        self._version_str: str = DEFAULT_VERSION
        self._load()

    # ── Okuma ────────────────────────────────────────────────

    def _load(self) -> None:
        """Dosyadan versiyon oku. Yoksa varsayılanı kullan ve kaydet."""
        if self._file.exists():
            raw = self._file.read_text(encoding="utf-8").strip()
            if raw and SEMVER_RE.match(raw):
                self._version_str = raw
                return
        # Dosya yoksa veya içerik bozuksa varsayılan yaz
        self._save()

    def _save(self) -> None:
        """Mevcut versiyonu dosyaya yaz."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(self._version_str.strip() + "\n", encoding="utf-8")

    @property
    def current(self) -> str:
        """Mevcut versiyon (örn: '0.1.0')."""
        return self._version_str

    @current.setter
    def current(self, value: str) -> None:
        """Versiyonu doğrudan set et (örn: '2.0.0')."""
        if not SEMVER_RE.match(value):
            raise VersionError(
                f"Geçersiz versiyon formatı: '{value}'. "
                f"Beklenen: major.minor.patch (örn: 1.2.3)"
            )
        self._version_str = value
        self._save()

    # ── Bump (artırma) ───────────────────────────────────────

    def bump_patch(self) -> str:
        """Patch sürümünü 1 artır: 0.1.0 → 0.1.1"""
        m = SEMVER_RE.match(self._version_str)
        if not m:
            raise VersionError(f"Mevcut versiyon ayrıştırılamadı: {self._version_str}")
        major, minor, patch, suffix = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        new = f"{major}.{minor}.{int(patch) + 1}{suffix}"
        self._version_str = new
        self._save()
        return self._version_str

    def bump_minor(self) -> str:
        """Minor sürümü 1 artır, patch'i sıfırla: 0.1.0 → 0.2.0"""
        m = SEMVER_RE.match(self._version_str)
        if not m:
            raise VersionError(f"Mevcut versiyon ayrıştırılamadı: {self._version_str}")
        major, minor, _, suffix = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        new = f"{major}.{int(minor) + 1}.0{suffix}"
        self._version_str = new
        self._save()
        return self._version_str

    def bump_major(self) -> str:
        """Major sürümü 1 artır, minor ve patch'i sıfırla: 0.1.0 → 1.0.0"""
        m = SEMVER_RE.match(self._version_str)
        if not m:
            raise VersionError(f"Mevcut versiyon ayrıştırılamadı: {self._version_str}")
        major, _, _, suffix = m.group(1), m.group(2), m.group(3), m.group(4) or ""
        new = f"{int(major) + 1}.0.0{suffix}"
        self._version_str = new
        self._save()
        return self._version_str

    # ── String temsili ───────────────────────────────────────

    def __str__(self) -> str:
        return self._version_str

    def __repr__(self) -> str:
        return f"<VersionManager version={self._version_str!r}>"


# ── Singleton benzeri kullanım ─────────────────────────────
_version_manager: VersionManager | None = None


def get_version_manager() -> VersionManager:
    """Global tekil versiyon yöneticisini döndürür."""
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
