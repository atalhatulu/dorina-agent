"""Güvenlik modülü - API key, onay, maskeleme."""

from __future__ import annotations
import os
from pathlib import Path


class Auth:
    """API key yönetimi."""

    ENV_FILE = Path(".env")

    def __init__(self):
        self.keys: dict[str, str] = {}
        self._load_env()

    def _load_env(self):
        """.env dosyasından key'leri oku."""
        from dotenv import load_dotenv
        load_dotenv()

        # Bilinen provider key'leri
        for var in [
            "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "GROQ_API_KEY",
            "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY",
            "GEMINI_API_KEY", "DORINA_API_KEY",
        ]:
            value = os.getenv(var)
            if value:
                self.keys[var] = value

    def get(self, key_name: str) -> str | None:
        return self.keys.get(key_name) or os.getenv(key_name)

    def set(self, key_name: str, value: str):
        """.env dosyasına key ekle."""
        self.keys[key_name] = value
        # .env'ye yaz
        if self.ENV_FILE.exists():
            content = self.ENV_FILE.read_text()
            if f"{key_name}=" in content:
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if line.startswith(f"{key_name}="):
                        lines[i] = f"{key_name}={value}"
                self.ENV_FILE.write_text("\n".join(lines))
            else:
                self.ENV_FILE.write_text(content.rstrip() + f"\n{key_name}={value}\n")
        else:
            self.ENV_FILE.write_text(f"{key_name}={value}\n")

    def list_providers(self) -> list[str]:
        """Kurulu provider'ları listele."""
        available = []
        for var in self.keys:
            name = var.replace("_API_KEY", "").lower()
            available.append(name)
        return available

    def has_key(self, provider: str) -> bool:
        env_var = f"{provider.upper()}_API_KEY"
        return env_var in self.keys


auth = Auth()
