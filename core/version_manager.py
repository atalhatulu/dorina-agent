"""
Version Manager — reads and persists the project version.

Usage:
    from core.version_manager import VersionManager

    v = VersionManager()
    print(v.current)        # "1.0.0"
    v.current = "1.1.0"     # set + persist to core/version.txt

Auto-saves to disk (core/version.txt).
"""

from __future__ import annotations
import re
from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parent / "version.txt"
DEFAULT_VERSION = "0.1.0"

# ── Semver regex: major.minor.patch (e.g. 1.2.3, 0.1.0-dev) ──
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(-.*)?$")


class VersionError(Exception):
    """Raised for version-related errors."""


class VersionManager:
    """Reads and persists the project version from/to a file."""

    def __init__(self, filepath: str | Path | None = None):
        self._file = Path(filepath) if filepath else VERSION_FILE
        self._version_str: str = DEFAULT_VERSION
        self._load()

    # ── Read ─────────────────────────────────────────────────

    def _load(self) -> None:
        """Read version from file. Use default if missing and save it."""
        if self._file.exists():
            raw = self._file.read_text(encoding="utf-8").strip()
            if raw and SEMVER_RE.match(raw):
                self._version_str = raw
                return
        # File missing or corrupt — write default
        self._save()

    def _save(self) -> None:
        """Write current version to file."""
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(self._version_str.strip() + "\n", encoding="utf-8")

    @property
    def current(self) -> str:
        """Current version string (e.g. '0.1.0')."""
        return self._version_str

    @current.setter
    def current(self, value: str) -> None:
        """Directly set version (e.g. '2.0.0')."""
        if not SEMVER_RE.match(value):
            raise VersionError(
                f"Invalid version format: '{value}'. "
                f"Expected: major.minor.patch (e.g. 1.2.3)"
            )
        self._version_str = value
        self._save()


    # ── String representation ────────────────────────────────

    def __str__(self) -> str:
        return self._version_str

    def __repr__(self) -> str:
        return f"<VersionManager version={self._version_str!r}>"


# ── Singleton-like access ──────────────────────────────────
_version_manager: VersionManager | None = None


def get_version_manager() -> VersionManager:
    """Return the global singleton version manager."""
    global _version_manager
    if _version_manager is None:
        _version_manager = VersionManager()
    return _version_manager
