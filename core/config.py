"""Yapılandırma yönetimi - pydantic-settings ile."""

from pathlib import Path
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource
from pydantic_settings.sources import PydanticBaseSettingsSource
from pydantic import Field
from core.constants import DORINA_HOME


class ModelConfig(BaseSettings):
    default: str = "deepseek/deepseek-chat"
    provider: str = "deepseek"
    fallback_providers: List[str] = ["openrouter", "groq"]
    context_length: int = 128000
    max_tokens: int = 4096
    # Token pricing (per 1K tokens USD)
    pricing: dict = {
        "deepseek/deepseek-chat": {"input": 0.00014, "output": 0.00028, "cached_input": 0.00007},
        "deepseek/deepseek-v4-flash": {"input": 0.00014, "output": 0.00028, "cached_input": 0.00007},
        "openrouter/anthropic/claude-sonnet-4": {"input": 0.003, "output": 0.015, "cached_input": 0.00015},
        "groq/llama3-70b-8192": {"input": 0.00059, "output": 0.00079, "cached_input": 0.0003},
        "default": {"input": 0.00015, "output": 0.0006, "cached_input": 0.000075},
    }
    active_model: str = ""  # set at runtime by provider router


class TerminalConfig(BaseSettings):
    status_bar: bool = True
    theme: str = "dark"
    markdown: bool = True


class MemoryConfig(BaseSettings):
    enabled: bool = True
    vector_store: str = "chroma"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    auto_extract: bool = True
    max_working_messages: int = 20


class ToolsConfig(BaseSettings):
    sandbox: str = "docker"
    approval_mode: str = "smart"
    mcp_enabled: bool = True


class SessionConfig(BaseSettings):
    storage: str = "sqlite"
    auto_save: bool = True
    max_sessions: int = 100


class SkillsConfig(BaseSettings):
    enabled: bool = True
    auto_detect: bool = True
    store_dir: str = "skills/store"


class SecurityConfig(BaseSettings):
    redact_secrets: bool = True
    block_destructive_commands: bool = True
    max_code_execution_time: int = 30
    # Approval listeleri — tool isimleri
    always_allow: list[str] = [
        "read_file", "search_files", "list_directory",
        "get_weather", "get_time", "web_search",
        "get_python_info", "process_list",
    ]
    ask_always: list[str] = [
        "delete_file", "rm", "batch_delete",
        "execute_code", "run_script",
        "db_execute", "container_exec",
        "bulk_execute_command",
    ]


class SoulConfig(BaseSettings):
    file: str = "soul.md"
    language: str = "tr"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=str(DORINA_HOME / "config.yaml"),
        env_file=".env",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )

    model: ModelConfig = ModelConfig()
    terminal: TerminalConfig = TerminalConfig()
    memory: MemoryConfig = MemoryConfig()
    tools: ToolsConfig = ToolsConfig()
    session: SessionConfig = SessionConfig()
    skills: SkillsConfig = SkillsConfig()
    security: SecurityConfig = SecurityConfig()
    soul: SoulConfig = SoulConfig()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Settings":
        """Load config.yaml + .env, return Settings."""
        import yaml
        from pathlib import Path as P

        config_path = P(path) if path else P("config.yaml")
        if config_path.exists():
            with open(config_path) as f:
                raw = yaml.safe_load(f)
        else:
            raw = {}

        # Read environment
        from dotenv import load_dotenv
        load_dotenv()

        return cls(**raw)


settings = Settings.load()
