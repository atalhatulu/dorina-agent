"""Plugin sistemi — manifest tabanlı, Pydantic doğrulamalı.

Plugin'ler plugins/store/<name>/ dizininde yaşar.
Her plugin bir manifest içerir: plugin.json veya plugin.yaml.
"""

from .schema import PluginManifest, PluginCommand, PluginSkill, load_manifest
from .manager import PluginManager, Plugin, plugin_manager

__all__ = [
    "PluginManifest", "PluginCommand", "PluginSkill", "load_manifest",
    "PluginManager", "Plugin", "plugin_manager",
]
