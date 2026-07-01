import json
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar('T')


def safe_json_loads(path_or_str: str | Path, default: T | None = None) -> dict | list | T:
    """JSON dosyasini veya string'i guvenli oku. Hata durumunda default doner."""
    try:
        if isinstance(path_or_str, Path) or (isinstance(path_or_str, str) and Path(path_or_str).exists()):
            return json.loads(Path(path_or_str).read_text(encoding='utf-8'))
        return json.loads(path_or_str)
    except (json.JSONDecodeError, FileNotFoundError, PermissionError, OSError):
        return default if default is not None else {}
