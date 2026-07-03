"""File History tools: snapshot, restore, diff, history."""
from __future__ import annotations
import json
from tools.registry import register_tool


@register_tool(
    name="history",
    description="Show file change history. Lists which files changed and when.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "History for a specific file (optional)", "default": ""},
            "limit": {"type": "integer", "description": "How many snapshots to show", "default": 10},
        },
    },
    toolset="history",
)
def history_tool(file: str = "", limit: int = 10) -> str:
    from history.file_history import file_history
    h = file_history.get_history(file, limit)
    if not h:
        return json.dumps({"snapshots": [], "message": "No snapshots"})
    return json.dumps({"snapshots": h, "stats": file_history.stats()}, ensure_ascii=False, indent=2)


@register_tool(
    name="restore",
    description="Restore file to a previous snapshot. Default: latest snapshot.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "File to restore"},
            "index": {"type": "integer", "description": "Snapshot index (-1=latest, -2=previous)", "default": -1},
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
    return json.dumps({"error": "Snapshot not found"})


@register_tool(
    name="diff_history",
    description="Show diff between current file and a snapshot.",
    parameters={
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "File path"},
            "index": {"type": "integer", "description": "Snapshot index", "default": -1},
        },
        "required": ["file"],
    },
    toolset="history",
)
def diff_history_tool(file: str, index: int = -1) -> str:
    from history.file_history import file_history
    d = file_history.diff(file, index)
    return d or "No differences"
