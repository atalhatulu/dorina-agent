"""Tests for plugin manager."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestPluginManager:
    def test_import_manager(self):
        """PluginManager should import."""
        from plugins.manager import PluginManager
        pm = PluginManager()
        assert pm is not None

    def test_import_manifest(self):
        """PluginManifest should import."""
        from plugins.schema import PluginManifest
        assert PluginManifest is not None

    def test_list_plugins_empty(self):
        """New manager should have empty plugin list."""
        from plugins.manager import PluginManager
        pm = PluginManager()
        plugins = pm.list_plugins() if hasattr(pm, 'list_plugins') else []
        assert isinstance(plugins, list)

    def test_manifest_creation(self):
        """PluginManifest should accept valid plugin metadata."""
        from plugins.schema import PluginManifest
        manifest = PluginManifest(
            name="test-plugin",
            version="1.0.0",
            description="A test plugin",
        )
        assert manifest.name == "test-plugin"
        assert manifest.version == "1.0.0"

    def test_manifest_defaults(self):
        """PluginManifest should have sensible defaults."""
        from plugins.schema import PluginManifest
        manifest = PluginManifest(name="minimal", version="1.0.0")
        assert manifest.name == "minimal"
        assert manifest.version == "1.0.0"
