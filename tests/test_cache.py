"""DiskCache testleri."""

import sys
import time
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestDiskCache:
    def test_set_and_get(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=3600)
        dc.set("test_key", {"value": 42})
        result = dc.get("test_key")
        assert result == {"value": 42}
        # Temizlik
        cache_file = dc.cache_dir / f"{hash('test_key')}.json"
        if cache_file.exists():
            cache_file.unlink()

    def test_get_nonexistent(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=3600)
        result = dc.get("this_key_does_not_exist_xyz")
        assert result is None

    def test_ttl_expiry(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=1)  # 1 saniye TTL
        dc.set("expire_key", "value")
        # Exists when fetched immediately
        assert dc.get("expire_key") is not None
        # Should be gone after TTL expires
        time.sleep(1.1)
        assert dc.get("expire_key") is None
        cache_file = dc.cache_dir / f"{hash('expire_key')}.json"
        if cache_file.exists():
            cache_file.unlink()

    def test_cache_creates_dir(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=3600)
        assert dc.cache_dir.exists()
        assert dc.cache_dir.is_dir()

    def test_overwrite_value(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=3600)
        dc.set("overwrite_key", "first_value")
        dc.set("overwrite_key", "second_value")
        result = dc.get("overwrite_key")
        assert result == "second_value"
        cache_file = dc.cache_dir / f"{hash('overwrite_key')}.json"
        if cache_file.exists():
            cache_file.unlink()

    def test_cache_different_keys(self):
        from cache.provider import DiskCache
        dc = DiskCache(ttl=3600)
        dc.set("key_a", "value_a")
        dc.set("key_b", "value_b")
        assert dc.get("key_a") == "value_a"
        assert dc.get("key_b") == "value_b"
        for key in ["key_a", "key_b"]:
            cache_file = dc.cache_dir / f"{hash(key)}.json"
            if cache_file.exists():
                cache_file.unlink()
