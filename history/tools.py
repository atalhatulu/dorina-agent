"""File History tool'lari: snapshot, restore, diff, history."""
from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="history",
    description="Dosya değişiklik geçmişini göster. Hangi dosyaların ne zaman değiştiğini listeler.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Belirli bir dosyanın geçmişi (opsiyonel)", "default": ""},
            "limit": {"type": "integer", "description": "Kaç snapshot gösterilecek", "default": 10},
        },
    },
    toolset="history",
)
def history_tool(file: str = "", limit: int = 10) -> str:
    from history.file_history import file_history
    h = file_history.get_history(file, limit)
    if not h:
        return json.dumps({"snapshots": [], "message": "Snapshot yok"})
    return json.dumps({"snapshots": h, "stats": file_history.stats()}, ensure_ascii=False, indent=2)


@register_tool(
    name="restore",
    description="Dosyayı önceki bir snapshot'a geri sar. Varsayılan: son snapshot.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Geri sarılacak dosya"},
            "index": {"type": "integer", "description": "Snapshot index (-1=son, -2=ondan onceki)", "default": -1},
        },
        "required": ["file"],
    },
    toolset="history",
)
def restore_tool(file: str, index: int = -1) -> str:
    from history.file_history import file_history
    result = file_history.restore(index, file)
    if result:
        return json.dumps({"restored": result, "snapshot_index": index})
    return json.dumps({"error": "Snapshot bulunamadi"})


@register_tool(
    name="diff_history",
    description="Mevcut dosya ile snapshot arasındaki farkı göster.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Dosya yolu"},
            "index": {"type": "integer", "description": "Snapshot index", "default": -1},
        },
        "required": ["file"],
    },
    toolset="history",
)
def diff_history_tool(file: str, index: int = -1) -> str:
    from history.file_history import file_history
    d = file_history.diff(file, index)
    return d or "Fark yok"
