"""Tests for core/version_manager.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestVersionManager:
    def test_load_default(self, tmp_path):
        from core.version_manager import VersionManager
        v = VersionManager(filepath=tmp_path / "version.txt")
        assert v.current == "0.1.0"

    def test_load_existing(self, tmp_path):
        from core.version_manager import VersionManager
        f = tmp_path / "version.txt"
        f.write_text("1.2.3\n")
        v = VersionManager(filepath=f)
        assert v.current == "1.2.3"

    def test_load_corrupt(self, tmp_path):
        from core.version_manager import VersionManager
        f = tmp_path / "version.txt"
        f.write_text("not-a-version\n")
        v = VersionManager(filepath=f)
        assert v.current == "0.1.0"

    def test_direct_set(self, tmp_path):
        from core.version_manager import VersionManager, VersionError
        v = VersionManager(filepath=tmp_path / "version.txt")
        v.current = "2.0.0"
        assert v.current == "2.0.0"

    def test_invalid_set_raises(self, tmp_path):
        from core.version_manager import VersionManager, VersionError
        v = VersionManager(filepath=tmp_path / "version.txt")
        with pytest.raises(VersionError):
            v.current = "invalid"

    def test_str_repr(self, tmp_path):
        from core.version_manager import VersionManager
        v = VersionManager(filepath=tmp_path / "version.txt")
        assert str(v) == "0.1.0"
        assert "VersionManager" in repr(v)

    def test_get_version_manager_singleton(self):
        from core.version_manager import get_version_manager
        v1 = get_version_manager()
        v2 = get_version_manager()
        assert v1 is v2
