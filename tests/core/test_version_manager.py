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

    def test_bump_patch(self, tmp_path):
        from core.version_manager import VersionManager
        v = VersionManager(filepath=tmp_path / "version.txt")
        result = v.bump_patch()
        assert result == "0.1.1"
        assert v.current == "0.1.1"

    def test_bump_minor(self, tmp_path):
        from core.version_manager import VersionManager
        v = VersionManager(filepath=tmp_path / "version.txt")
        result = v.bump_minor()
        assert result == "0.2.0"
        assert v.current == "0.2.0"

    def test_bump_major(self, tmp_path):
        from core.version_manager import VersionManager
        v = VersionManager(filepath=tmp_path / "version.txt")
        result = v.bump_major()
        assert result == "1.0.0"
        assert v.current == "1.0.0"

    def test_persists_to_file(self, tmp_path):
        from core.version_manager import VersionManager
        f = tmp_path / "version.txt"
        v = VersionManager(filepath=f)
        v.bump_patch()
        v2 = VersionManager(filepath=f)
        assert v2.current == "0.1.1"

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

    def test_bump_with_suffix(self, tmp_path):
        from core.version_manager import VersionManager
        f = tmp_path / "version.txt"
        f.write_text("0.1.0-dev\n")
        v = VersionManager(filepath=f)
        assert v.bump_patch() == "0.1.1-dev"
        assert v.bump_minor() == "0.2.0-dev"
        assert v.bump_major() == "1.0.0-dev"

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
