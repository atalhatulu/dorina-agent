"""Plugin manifest schema — Pydantic model for plugin.json / plugin.yaml manifests.

Claude Code plugin.json standardına benzer şekilde tasarlanmıştır.
Her plugin bir manifest dosyası içerir: plugin.json veya plugin.yaml.

Schema:
    name: str (required)
    version: str (required, semver)
    description: str
    author: str
    hooks: list[str] — lifecycle hook names (on_session_start, on_tool_call, etc.)
    commands: list[dict] — slash commands the plugin registers
    skills: list[dict] — skills the plugin provides
    dependencies: list[str] — pip package names
    python: str — required Python version (e.g., ">=3.10")
"""

from __future__ import annotations
from typing import Optional
from pathlib import Path
from pydantic import BaseModel, Field, field_validator
import json
import re


class PluginCommand(BaseModel):
    """A slash command registered by a plugin."""
    name: str = Field(description="Command name without / prefix, e.g. 'greet'")
    description: str = Field(default="", description="Short help text")
    parameters: dict = Field(default_factory=dict, description="JSON schema for arguments")


class PluginSkill(BaseModel):
    """A skill provided by a plugin."""
    name: str = Field(description="Skill identifier")
    description: str = Field(default="", description="What this skill does")
    triggers: list[str] = Field(default_factory=list, description="Keywords that trigger this skill")


class PluginManifest(BaseModel):
    """Plugin manifest — plugin.json / plugin.yaml schema.

    Minimal example:
        {
            "name": "my-plugin",
            "version": "1.0.0",
            "description": "Does something useful",
            "hooks": ["on_tool_called"],
            "commands": [{"name": "greet", "description": "Says hello"}],
            "dependencies": ["requests>=2.0"]
        }
    """
    name: str = Field(..., description="Plugin name (unique identifier)")
    version: str = Field(..., description="Semantic version (e.g., 1.0.0)")
    description: str = Field(default="", description="Human-readable description")
    author: str = Field(default="", description="Plugin author")

    hooks: list[str] = Field(
        default_factory=list,
        description="Lifecycle hooks this plugin registers",
        examples=[["on_session_start", "on_tool_called", "on_message"]],
    )
    commands: list[PluginCommand] = Field(
        default_factory=list,
        description="Slash commands the plugin contributes",
    )
    skills: list[PluginSkill] = Field(
        default_factory=list,
        description="Skills the plugin contributes to the agent",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="Python package dependencies (pip format)",
        examples=[["requests>=2.0", "beautifulsoup4>=4.12"]],
    )
    python: str = Field(default=">=3.10", description="Required Python version")

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not re.match(r"^\d+\.\d+\.\d+", v):
            raise ValueError(f"Version must be semver format (e.g., 1.0.0), got: {v}")
        return v

    @field_validator("name")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]+$", v):
            raise ValueError(f"Plugin name must start with a letter, got: {v}")
        return v

    def to_json(self, indent: int = 2) -> str:
        """Serialize manifest to JSON string."""
        return self.model_dump_json(exclude_none=True, indent=indent)

    def to_dict(self) -> dict:
        """Serialize manifest to dict."""
        return self.model_dump(exclude_none=True)


def load_manifest(path: Path | str) -> PluginManifest | None:
    """Load a plugin manifest from plugin.json or plugin.yaml.

    Args:
        path: Path to plugin directory or manifest file.

    Returns:
        PluginManifest if found and valid, None otherwise.
    """
    path = Path(path)
    if path.is_dir():
        # Look for manifest file in directory
        candidates = [path / "plugin.json", path / "plugin.yaml", path / "plugin.yml"]
        for c in candidates:
            if c.exists():
                path = c
                break
        else:
            return None

    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(raw)
        except ImportError:
            raise ImportError("PyYAML required for .yaml manifest files: pip install pyyaml")
    else:
        data = json.loads(raw)

    if not isinstance(data, dict):
        return None

    return PluginManifest(**data)
