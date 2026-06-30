"""Tests for core/config.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestModelConfig:
    def test_default_values(self):
        from core.config import ModelConfig
        cfg = ModelConfig()
        assert cfg.default == "deepseek/deepseek-chat"
        assert cfg.provider == "deepseek"
        assert cfg.context_length == 128000
        assert cfg.max_tokens == 4096

    def test_pricing_defaults(self):
        from core.config import ModelConfig
        cfg = ModelConfig()
        assert "deepseek/deepseek-chat" in cfg.pricing
        assert "default" in cfg.pricing
        assert cfg.pricing["default"]["input"] > 0
        assert cfg.pricing["default"]["output"] > 0


class TestSettings:
    def test_settings_nested_configs(self):
        from core.config import Settings
        s = Settings()
        assert s.model.default in ("deepseek/deepseek-chat", "deepseek/deepseek-v4-flash", "google/gemini-2.0-flash", "gemini/gemini-2.0-flash", "ollama/gemma4:e2b", "ollama/nemotron-3-super:cloud")
        assert s.terminal.status_bar is True
        assert s.memory.enabled is True
        assert s.tools.sandbox == "docker"

    def test_security_config(self):
        from core.config import Settings
        s = Settings()
        assert "read_file" in s.security.always_allow
        assert "delete_file" in s.security.ask_always
        assert s.security.redact_secrets is True
        assert s.security.max_code_execution_time == 30

    def test_soul_config(self):
        from core.config import Settings
        s = Settings()
        # language may be set from env, just check it's a string
        assert isinstance(s.soul.language, str)
        assert s.soul.file == "soul.md"

    def test_session_config(self):
        from core.config import Settings
        s = Settings()
        assert s.session.storage == "sqlite"
        assert s.session.auto_save is True
        assert s.session.max_sessions == 100

    def test_tools_config(self):
        from core.config import Settings
        s = Settings()
        assert s.tools.approval_mode == "smart"
        assert s.tools.mcp_enabled is True


class TestSettingsLoad:
    def test_load_without_file(self, tmp_path):
        from core.config import Settings
        s = Settings.load()
        assert s is not None
        assert s.model.default is not None


class TestTerminalConfig:
    def test_terminal_defaults(self):
        from core.config import TerminalConfig
        t = TerminalConfig()
        assert t.theme == "dark"
        assert t.markdown is True
        assert t.status_bar is True


class TestMemoryConfig:
    def test_memory_defaults(self):
        from core.config import MemoryConfig
        m = MemoryConfig()
        assert m.vector_store == "chroma"
        assert m.auto_extract is True
        assert m.max_working_messages == 20


class TestSkillsConfig:
    def test_skills_defaults(self):
        from core.config import SkillsConfig
        s = SkillsConfig()
        assert s.enabled is True
        assert s.auto_detect is True
        assert s.store_dir == "~/.dorina/skills"
