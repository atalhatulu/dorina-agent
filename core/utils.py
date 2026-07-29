import json
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar('T')


def safe_json_loads(path_or_str: str | Path, default: T | None = None) -> dict | list | T:
    """JSON dosyasini veya string'i guvenli oku. Hata durumunda default doner."""
    fallback = default if default is not None else {}
    if isinstance(path_or_str, Path):
        try:
            return json.loads(path_or_str.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            return fallback

    if isinstance(path_or_str, str):
        # 1. Direct JSON string parse attempt
        try:
            return json.loads(path_or_str)
        except (json.JSONDecodeError, TypeError):
            pass
        # 2. File path attempt (only for reasonably short strings)
        if len(path_or_str) < 512:
            try:
                p = Path(path_or_str)
                if p.is_file():
                    return json.loads(p.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                pass
    return fallback
