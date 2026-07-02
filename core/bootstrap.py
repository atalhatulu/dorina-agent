"""Uygulama baslatma — env ayarlari, log supurasyonu, API key yukleme.

main.py'den cikarilmistir: bu modul startup'ta bir kez cagrilir.
"""

from __future__ import annotations
import os
import sys
import warnings
from pathlib import Path


def suppress_noisy_logs():
    """LLM kutuphanelerinin gereksiz log'larini sustur."""
    os.environ.setdefault("LITELLM_LOG", "WARNING")
    os.environ.setdefault("OPENAI_LOG_LEVEL", "WARNING")
    os.environ.setdefault("LITELLM_SUPPRESS_DEBUG_INFO", "1")
    os.environ.setdefault("LITELLM_VERBOSE", "False")
    os.environ.setdefault("LITELLM_DEBUG", "False")
    os.environ.setdefault("LITELLM_DISABLE_LOGS", "True")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    warnings.filterwarnings("ignore", message="Cannot enable progress bars")


def ensure_project_root():
    """Proje kokunu PYTHONPATH'e ekle."""
    _root = str(Path(__file__).resolve().parent.parent)
    if _root not in sys.path:
        sys.path.insert(0, _root)


def init_api_keys():
    """Load all API keys from KeyManager into environment."""
    from providers.keys import keys, ENV_MAP
    for provider, ev in ENV_MAP.items():
        if not ev:
            continue
        k = keys.get_key(provider)
        if k and not os.environ.get(ev):
            os.environ[ev] = k
