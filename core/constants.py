"""Global sabitler ve yollar."""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional

from core.version_manager import get_version_manager

NAME = "dorina-agent"

# Dorina home directory — tum kullanici verileri burada
DORINA_HOME = Path.home() / ".dorina"

# Default paths under DORINA_HOME
DEFAULT_CONFIG = DORINA_HOME / "config.yaml"
DEFAULT_DATA_DIR = DORINA_HOME / "data"
DEFAULT_SESSIONS_DIR = DORINA_HOME / "sessions"
DEFAULT_EXPORT_DIR = DORINA_HOME / "export"
DEFAULT_LOGS_DIR = DORINA_HOME / "logs"
DEFAULT_KNOWLEDGE_DIR = DORINA_HOME / "knowledge"
DEFAULT_CACHE_DIR = DORINA_HOME / "data" / "cache"
DEFAULT_CHROMA_DIR = DORINA_HOME / "data" / "rag_knowledge"
DEFAULT_BG_TOOLS_DIR = DORINA_HOME / "bg_tools"

# Kullanici calisma alani
DEFAULT_WORKSPACE = Path.home() / "Documents" / "DorinaProjects"


def ensure_dorina_home():
    """~/.dorina/ altinda gerekli dizinleri olustur."""
    for d in [DORINA_HOME, DEFAULT_DATA_DIR, DEFAULT_SESSIONS_DIR, DEFAULT_EXPORT_DIR,
              DEFAULT_LOGS_DIR, DEFAULT_KNOWLEDGE_DIR, DEFAULT_CACHE_DIR, DEFAULT_CHROMA_DIR,
              DEFAULT_BG_TOOLS_DIR, DORINA_HOME / "skills", DORINA_HOME / "memories",
              DEFAULT_WORKSPACE]:
        d.mkdir(parents=True, exist_ok=True)
    # config.yaml yoksa example'dan kopyala
    if not DEFAULT_CONFIG.exists():
        example = Path(__file__).resolve().parent.parent / "config.yaml.example"
        if example.exists():
            DEFAULT_CONFIG.write_text(example.read_text())
            print(f"  [info] Config olusturuldu: {DEFAULT_CONFIG}")
    # soul.md yoksa projedekinden kopyala
    _soul_path = DORINA_HOME / "SOUL.md"
    if not _soul_path.exists():
        _soul_example = Path(__file__).resolve().parent.parent / "soul.md"
        if _soul_example.exists():
            _soul_path.write_text(_soul_example.read_text())
            print(f"  [info] soul.md olusturuldu: {_soul_path}")

    # Sistem dizinlerini tara (bir kere)
    _sys_mem = DORINA_HOME / "memories" / "SYSTEM.md"
    if not _sys_mem.exists():
        _lines = []
        for _dir_name, _path in [("MASAUSTU", Path.home() / "Desktop"),
                                  ("BELGELER", Path.home() / "Documents"),
                                  ("INDIRILENLER", Path.home() / "Downloads")]:
            if _path.exists():
                _items = [f.name for f in _path.iterdir()][:20]
                _lines.append(f"- {_dir_name}: {_path} ({len(_items)} oge)")
                if _items:
                    _lines.append(f"  * {', '.join(_items[:8])}")
        _lines.append(f"- DORINA_HOME: {DORINA_HOME}")
        _lines.append(f"- PROJE: {Path(__file__).resolve().parent.parent}")
        _sys_mem.write_text("\n".join(_lines) + "\n")
        print(f"  [info] Sistem hafizasi olusturuldu: {_sys_mem}")


# Version from VersionManager — dinamik, dosyadan okur
def _get_version() -> str:
    try:
        return get_version_manager().current
    except Exception:
        return "0.1.0"

VERSION = _get_version()

# Project root directory (where pyproject.toml is)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# i18n paths
I18N_DIR = Path(__file__).resolve().parent / "i18n"

# Default language
DEFAULT_LANGUAGE = "en"

# Agent states
STATE_IDLE = "idle"
STATE_THINKING = "thinking"
STATE_ACTING = "acting"
STATE_DONE = "done"
STATE_ERROR = "error"

# Default model
DEFAULT_MODEL = ""
DEFAULT_PROVIDER = "deepseek"

# Token limitleri
MAX_WORKING_MESSAGES = 8  # ~2-3 tur konusma, session zaten gecmisi tutuyor
MAX_TOOL_CALLS_PER_TURN = 999  # tool_test_all icin limitsiz
MAX_TURNS = 50

# Memory types
MEMORY_WORKING = "working"
MEMORY_EPISODIC = "episodic"
MEMORY_SEMANTIC = "semantic"
MEMORY_PROCEDURAL = "procedural"

# ── P0-05: Skill Trigger Conditions ─────────────────────────────
# Session başlangıcında skill injection için trigger condition'ları
SKILL_TRIGGER_KEYWORDS = {
    "code": {"python", "javascript", "rust", "go", "code", "yazılım", "program", "debug", "hata ayıkla", "refactor", "test yaz",
             "review", "testing", "implementation", "engineering", "security", "optimization", "simplification",
             "maintain", "quality", "incremental", "interface", "design", "spec",
             "error", "recovery", "triage", "branch", "task", "build", "vertical slice",
             "test", "tests", "tester", "prove"},
    "devops": {"docker", "kubernetes", "k8s", "deploy", "ci/cd", "pipeline", "nginx", "linux", "sunucu", "server",
               "ci", "cd", "migration", "rollback", "release", "version", "git", "shipping", "automation",
               "observability", "instrumentation", "monitoring"},
    "data": {"veri", "data", "analiz", "analytics", "pandas", "sql", "database", "csv", "json", "api",
             "integra", "interface", "observability", "instrumentation"},
    "web": {"web", "frontend", "backend", "react", "vue", "api", "rest", "html", "css", "javascript",
            "browser", "ui", "ux", "devtools", "performance", "responsive"},
    "research": {"araştır", "research", "doküman", "document", "wiki", "öğren", "learn", "nedir", "what is",
                 "documentation", "spec", "specification", "interview", "idea", "planning",
                 "source", "doubt", "adr", "architecture",
                 "refine", "explore", "convergent", "divergent", "meta", "guideline"},
}

# Session başlangıcında hangi skill'lerin otomatik yükleneceği
SKILL_AUTO_LOAD_THRESHOLD = 2  # Kaç keyword eşleşirse skill otomatik yüklenir

# ── P0-06: Prompt Caching ──────────────────────────────────────
# Cache TTL (saniye)
CACHE_TTL = 3600  # 1 saat

# Maximum cache boyutu (karakter)
MAX_CACHE_SIZE = 100000  # 100KB

# Provider-specific cache control
CACHE_ENABLED_PROVIDERS = {"deepseek", "anthropic"}

# Cache stratejisi
CACHE_STRATEGY = "conservative"


# ═══════════════════════════════════════════════════════════════
# i18n (Internationalization) Helper
# ═══════════════════════════════════════════════════════════════

_i18n_cache: dict[str, dict[str, str]] = {}
_current_language: str = DEFAULT_LANGUAGE


def set_language(lang: str):
    """Set active language for i18n messages."""
    global _current_language
    _current_language = lang


def get_language() -> str:
    """Get the currently active language code."""
    return _current_language


def _load_translations(lang: str) -> dict[str, str]:
    """Load translation file for a language (with caching)."""
    if lang in _i18n_cache:
        return _i18n_cache[lang]

    filepath = I18N_DIR / f"{lang}.json"
    if not filepath.exists():
        # Fallback to English if requested language doesn't exist
        if lang != "en":
            return _load_translations("en")
        return {}

    try:
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
            _i18n_cache[lang] = data
            return data
    except Exception:
        return {}


def t(key: str, **kwargs) -> str:
    """Translate a key to the current language with optional format variables.

    Usage:
        t("error_not_found_file", path="/tmp/test.txt")
        t("error_generic", message="Something broke")
        t("info_loaded_skills", count=42)
    """
    translations = _load_translations(_current_language)
    template = translations.get(key)

    if template is None:
        # Fallback to English
        en_translations = _load_translations("en")
        template = en_translations.get(key, key)

    if kwargs:
        try:
            return template.format(**kwargs)
        except KeyError:
            return template

    return template


def load_language_from_config(config_path: Optional[Path] = None) -> str:
    """Load language setting from config.yaml.

    Looks for:
      - soul.language (from config.yaml)
      - language (top-level, from config.yaml)

    Returns the language code (tr, en, etc).
    """
    import yaml

    path = config_path or DEFAULT_CONFIG
    if not path.exists():
        return DEFAULT_LANGUAGE

    try:
        with open(path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return DEFAULT_LANGUAGE

    # Check soul.language first, then top-level language
    lang = (
        cfg.get("soul", {}).get("language")
        or cfg.get("language")
        or DEFAULT_LANGUAGE
    )
    set_language(lang)
    return lang
