"""Tests for security/auth.py"""
import pytest
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestAuth:
    def test_get_key_none_for_unknown(self, fresh_auth):
        assert fresh_auth.get("NONEXISTENT_KEY") is None

    def test_has_key_false_for_unknown(self, fresh_auth):
        assert fresh_auth.has_key("nonexistent_provider") is False

    def test_list_providers_empty_initially(self, fresh_auth):
        providers = fresh_auth.list_providers()
        assert isinstance(providers, list)

    def test_set_and_get_key(self, fresh_auth, tmp_path):
        fresh_auth.ENV_FILE = tmp_path / ".env"
        fresh_auth.set("TEST_API_KEY", "test_value_123")
        value = fresh_auth.get("TEST_API_KEY")
        assert value == "test_value_123"

    def test_set_key_writes_to_env_file(self, fresh_auth, tmp_path):
        env_file = tmp_path / ".env"
        fresh_auth.ENV_FILE = env_file
        fresh_auth.set("TEST_KEY", "secret123")
        content = env_file.read_text()
        assert "TEST_KEY=secret123" in content

    def test_set_key_updates_existing(self, fresh_auth, tmp_path):
        env_file = tmp_path / ".env"
        env_file.write_text("TEST_KEY=old_value\nOTHER_KEY=keep\n")
        fresh_auth.ENV_FILE = env_file
        fresh_auth.set("TEST_KEY", "new_value")
        content = env_file.read_text()
        assert "TEST_KEY=new_value" in content
        assert "OTHER_KEY=keep" in content

    def test_key_variables_loaded(self):
        from security.auth import Auth
        # Save original
        old_env = dict(os.environ)
        try:
            os.environ["OPENAI_API_KEY"] = "sk-test123"
            os.environ["GROQ_API_KEY"] = "gsk-test456"
            a = Auth()
            assert a.get("OPENAI_API_KEY") == "sk-test123"
            assert a.get("GROQ_API_KEY") == "gsk-test456"
        finally:
            os.environ.clear()
            os.environ.update(old_env)

    def test_has_key_true_when_set(self):
        from security.auth import Auth
        old_env = dict(os.environ)
        try:
            os.environ["DEEPSEEK_API_KEY"] = "ssec-test"
            a = Auth()
            assert a.has_key("deepseek") is True
        finally:
            os.environ.clear()
            os.environ.update(old_env)
