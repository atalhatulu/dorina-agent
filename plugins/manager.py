"""Plugin loader + manager — manifest parsing, lifecycle management, event hooks.

Claude Code plugin.json standardına benzer manifest tabanlı plugin sistemi.
Her plugin bir manifest (plugin.json/plugin.yaml) ve opsiyonel kod içerir.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Callable, Optional
import importlib
import importlib.util
import sys
import os

from core.logger import log
from core.event_bus import bus
from plugins.schema import PluginManifest, load_manifest

PLUGINS_DIR = Path(__file__).resolve().parent / "store"


class Plugin:
    """A loaded plugin with manifest, module, and lifecycle hooks."""

    def __init__(
        self,
        manifest: PluginManifest,
        module=None,
        hooks: dict[str, Callable] = None,
        path: Path = None,
    ):
        self.manifest = manifest
        self.module = module
        self.hooks: dict[str, Callable] = hooks or {}
        self.path: Path = path or PLUGINS_DIR / manifest.name
        self.enabled = True
        self._subscriptions: list[tuple[str, str]] = []  # (event_name, subscriber_id)

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def version(self) -> str:
        return self.manifest.version

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.manifest.description,
            "hooks": list(self.hooks.keys()),
            "commands": [c.name for c in self.manifest.commands],
            "skills": [s.name for s in self.manifest.skills],
            "enabled": self.enabled,
        }


class PluginManager:
    """Plugin lifecycle manager — discover, load, unload, reload.

    Lifecycle:
        1. discover() — scan plugins/store/ for plugin directories with manifests
        2. load(name) — parse manifest → validate → import module → register hooks
        3. unload(name) — remove hooks → clean up
        4. reload(name) — unload + load

    Event hooks are registered via the event bus (core.event_bus).
    """

    def __init__(self):
        self.plugins: dict[str, Plugin] = {}
        PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Discovery ────────────────────────────────────────────────

    def discover(self) -> list[str]:
        """Scan plugins/store/ for plugin directories with valid manifests.

        Returns:
            List of plugin names found (not yet loaded).
        """
        found = []
        for d in sorted(PLUGINS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            # Skip __pycache__ and hidden dirs
            if d.name == "__pycache__":
                continue
            manifest = self._find_manifest(d)
            if manifest:
                found.append(manifest.name)
            else:
                # Fallback: any dir with __init__.py is a valid plugin
                if (d / "__init__.py").exists():
                    found.append(d.name)
        return found

    def _find_manifest(self, directory: Path) -> PluginManifest | None:
        """Try to find and parse a manifest in the given directory."""
        try:
            return load_manifest(directory)
        except Exception as e:
            log.debug(f"Manifest parse error in {directory.name}: {e}")
            return None

    # ── Load / Unload ────────────────────────────────────────────

    def load(self, name: str) -> Optional[Plugin]:
        """Load a plugin by name.

        Steps:
            1. Find plugin directory in plugins/store/<name>/
            2. Try to load plugin.json/plugin.yaml manifest
            3. Validate manifest with Pydantic schema
            4. Import Python module if __init__.py exists
            5. Discover hooks (callables starting with on_)
            6. Register event bus subscriptions
            7. Emit plugin:loaded event

        Returns:
            Plugin instance, or None if not found/invalid.
        """
        plugin_path = PLUGINS_DIR / name
        if not plugin_path.exists() or not plugin_path.is_dir():
            log.warning(f"Plugin directory not found: {plugin_path}")
            return None

        # ── 1. Load manifest ──
        manifest = self._find_manifest(plugin_path)
        if manifest is None and (plugin_path / "__init__.py").exists():
            # Legacy fallback: create minimal manifest from directory name
            manifest = PluginManifest(name=name, version="0.1.0")
            log.debug(f"No manifest for '{name}', using legacy fallback")

        if manifest is None:
            log.warning(f"No manifest or __init__.py for '{name}' at {plugin_path}")
            return None

        # ── 2. Check dependencies (optional) ──
        if manifest.dependencies:
            missing = self._check_dependencies(manifest.dependencies)
            if missing:
                log.warning(
                    f"Plugin '{name}' missing dependencies: {', '.join(missing)}. "
                    f"Install with: pip install {' '.join(missing)}"
                )

        # ── 3. Import module ──
        module = None
        init_py = plugin_path / "__init__.py"
        if init_py.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"plugins.store.{name}",
                    init_py,
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[f"plugins.store.{name}"] = module
                    spec.loader.exec_module(module)
            except Exception as e:
                log.error(f"Failed to import plugin '{name}': {e}")
                # Allow loading without module (manifest-only plugins)
                module = None

        # ── 4. Discover hooks ──
        hooks: dict[str, Callable] = {}
        if module:
            for attr_name in dir(module):
                if attr_name.startswith("on_"):
                    attr = getattr(module, attr_name)
                    if callable(attr):
                        hooks[attr_name] = attr

        # ── 5. Create plugin object ──
        plugin = Plugin(manifest=manifest, module=module, hooks=hooks, path=plugin_path)

        # ── 6. Register event bus subscriptions ──
        self._register_hooks(plugin)

        self.plugins[name] = plugin
        bus.publish("plugin:loaded", name=name, plugin=plugin)
        log.info(f"Plugin loaded: {name} v{manifest.version} ({len(hooks)} hooks, {len(manifest.commands)} commands)")
        return plugin

    def load_plugin(self, name: str) -> Optional[Plugin]:
        """Alias for load()."""
        return self.load(name)

    def unload(self, name: str) -> bool:
        """Unload a plugin: remove hooks, clean up.

        Returns:
            True if unloaded, False if not found.
        """
        if name not in self.plugins:
            log.warning(f"Cannot unload '{name}': not loaded")
            return False

        plugin = self.plugins[name]
        self._unregister_hooks(plugin)
        plugin.enabled = False

        # Remove from sys.modules if we added it
        mod_key = f"plugins.store.{name}"
        if mod_key in sys.modules:
            del sys.modules[mod_key]

        del self.plugins[name]
        bus.publish("plugin:unloaded", name=name)
        log.info(f"Plugin unloaded: {name}")
        return True

    def unload_plugin(self, name: str) -> bool:
        """Alias for unload()."""
        return self.unload(name)

    def reload(self, name: str) -> Optional[Plugin]:
        """Reload a plugin (unload + load)."""
        self.unload(name)
        return self.load(name)

    # ── Hook Registration ───────────────────────────────────────

    def _register_hooks(self, plugin: Plugin):
        """Register all hooks of a plugin on the event bus."""
        for hook_name, hook_fn in plugin.hooks.items():
            event_name = hook_name[3:]  # "on_tool_called" → "tool_called"
            subscriber_id = f"plugin:{plugin.name}"
            bus.subscribe(event_name, hook_fn, subscriber_id)
            plugin._subscriptions.append((event_name, subscriber_id))

    def _unregister_hooks(self, plugin: Plugin):
        """Remove all event bus subscriptions for a plugin."""
        for event_name, subscriber_id in plugin._subscriptions:
            bus.unsubscribe(event_name, subscriber_id)
        plugin._subscriptions.clear()

    # ── Dependency Management ────────────────────────────────────

    def _check_dependencies(self, deps: list[str]) -> list[str]:
        """Check which pip dependencies are missing.

        Returns:
            List of missing package names.
        """
        missing = []
        for dep in deps:
            # Handle version specifiers: "requests>=2.0" → "requests"
            pkg_name = dep.split(">=")[0].split("==")[0].split("<=")[0].split("!=")[0].strip()
            try:
                importlib.import_module(pkg_name.replace("-", "_"))
            except ImportError:
                # Some packages install with different names — check via pkg_resources
                try:
                    import pkg_resources  # type: ignore
                    pkg_resources.get_distribution(pkg_name)
                except (ImportError, pkg_resources.DistributionNotFound):
                    missing.append(dep)
        return missing

    # ── Query ────────────────────────────────────────────────────

    def get_plugin(self, name: str) -> Optional[Plugin]:
        """Get a loaded plugin by name."""
        return self.plugins.get(name)

    def list_plugins(self) -> list[dict]:
        """List all loaded plugins with metadata."""
        return [p.to_dict() for p in self.plugins.values()]

    def count(self) -> int:
        """Number of loaded plugins."""
        return len(self.plugins)

    def find_by_hook(self, hook_name: str) -> list[Plugin]:
        """Find all plugins that register a specific hook."""
        return [p for p in self.plugins.values() if hook_name in p.hooks]

    def find_by_command(self, command_name: str) -> list[Plugin]:
        """Find all plugins that register a specific command."""
        return [
            p for p in self.plugins.values()
            if any(c.name == command_name for c in p.manifest.commands)
        ]

    # ── Batch Operations ─────────────────────────────────────────

    def load_all(self) -> list[Plugin]:
        """Discover and load all plugins found in plugins/store/.

        Returns:
            List of successfully loaded plugins.
        """
        loaded = []
        for name in self.discover():
            try:
                plugin = self.load(name)
                if plugin:
                    loaded.append(plugin)
            except Exception as e:
                log.error(f"Failed to load plugin '{name}': {e}")
        return loaded

    def unload_all(self):
        """Unload all plugins."""
        for name in list(self.plugins.keys()):
            self.unload(name)

    def reload_all(self) -> list[Plugin]:
        """Reload all plugins."""
        self.unload_all()
        return self.load_all()


# Global singleton
plugin_manager = PluginManager()
