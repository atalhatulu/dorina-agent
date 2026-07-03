"""File tools — read, write, search, patch."""

from __future__ import annotations
import asyncio
import json
import subprocess
from pathlib import Path

from tools.registry import register_tool
from core.constants import DORINA_HOME
from core.utils import safe_json_loads
from tools.security import is_blocked_path, safe_resolve
from core.logger import log


# ─── FILE READ ─────────────────────────────────────────────

def _search_file_broad(filename: str, limit_hits: int = 5) -> list:
    """Search file across CWD, home, Downloads, Desktop, Documents."""
    from pathlib import Path as _Path

    # If /root/... path given but root doesn't exist, convert to home
    p = _Path(filename)
    if str(p).startswith("/root/") and not p.exists():
        alt = _Path(str(p).replace("/root/", str(_Path.home()) + "/", 1))
        if alt.exists():
            return [alt]

    dirs = [
        _Path.cwd(),
        _Path.home(),
        _Path.home() / "Downloads",
        _Path.home() / "Desktop",
        _Path.home() / "Documents",
    ]
    # Remove duplicates and non-existent dirs
    seen = set()
    search_dirs = []
    for d in dirs:
        r = d.resolve()
        if r.exists() and str(r) not in seen:
            seen.add(str(r))
            search_dirs.append(r)
    name = _Path(filename).name
    stem = _Path(filename).stem
    matches = []
    for d in search_dirs:
        for m in list(d.rglob(f"*{name}*"))[:limit_hits]:
            matches.append(m)
        if len(matches) >= limit_hits:
            break
    if len(matches) < limit_hits:
        for d in search_dirs:
            for m in list(d.rglob(f"*{stem}*"))[:limit_hits]:
                if m not in matches:
                    matches.append(m)
            if len(matches) >= limit_hits:
                break
    return matches[:limit_hits]


@register_tool(
    name="read_file",
    description="Read file. Pagination with offset/limit.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Dosya yolu"},
            "start_line": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
            "end_line": {"type": "integer", "description": "End line (optional)"},
            "limit": {"type": "integer", "description": "Number of lines to read", "default": 200},
            "offset": {"type": "integer", "description": "Start line (alternative)", "default": 1},
        },
        "required": ["path"],
    },
    toolset="file",
)
def read_file_tool(path: str, start_line: int = None, end_line: int = None, limit: int = 200, offset: int = None) -> str:
    """Read file content with line numbers, pagination, and binary protection."""
    log.debug("read_file_tool called: path=%r limit=%r start=%r end=%r offset=%r",
              path, limit, start_line, end_line, offset)
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    # Path traversal protection — only allow cwd + user directories
    _h = Path.home()
    _allowed = [
        str(Path.cwd()),
        str(_h / "Desktop"),
        str(_h / "Documents"),
        str(_h / "Downloads"),
        str(_h / ".dorina"),
        "/tmp",
    ]
    try:
        p = safe_resolve(str(p), _allowed)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    if not p.exists():
        # Map Turkish dir names → English (for users with Turkish locale)
        _tr_map = {"Masaüstü": "Desktop", "Masaustu": "Desktop", "İndirilenler": "Downloads", "Indirilenler": "Downloads", "Belgeler": "Documents", "Resimler": "Pictures", "Müzik": "Music", "Video": "Videos"}
        _path_str = str(p)
        for _tr, _en in _tr_map.items():
            if _tr in _path_str:
                _fixed = Path(_path_str.replace(_tr, _en))
                if _fixed.exists():
                    p = _fixed
                    break
        else:
            # Try broad search if still not found
            matches = _search_file_broad(path)
            if matches:
                p = Path(matches[0])
            else:
                return json.dumps({"error": f"File not found: {path}"})

    if p.is_dir():
        return json.dumps({
            "error": "The specified path is a DIRECTORY. 'read_file' can only read files.",
            "suggestion": "Use the 'terminal' tool with 'ls -la' or 'tree' to view directory contents."
        })

    # 1. Binary check
    try:
        with open(p, "rb") as bf:
            chunk = bf.read(1024)
            if b"\x00" in chunk:
                return json.dumps({
                    "error": "This file appears to be BINARY (not text). Read blocked.",
                    "path": str(p),
                    "size": p.stat().st_size
                })
    except (OSError, ValueError) as e:
        return json.dumps({"error": f"Error reading file: {e}"})

    # Normalize parameters
    _start = start_line if start_line is not None else (offset if offset is not None else 1)

    if end_line is not None:
        _limit = (end_line - _start) + 1
    else:
        _limit = limit

    if _limit <= 0:
        return json.dumps({"error": "Invalid line range (end_line < start_line)"})
    if _limit > 2000:
        _limit = 2000 # Hard cap for safety

    total = 0
    collected = []

    # ── Per-file read budget ──
    if not hasattr(read_file_tool, "_read_budget"):
        read_file_tool._read_budget = {}
    _budget_key = str(p.resolve())
    _already_read = read_file_tool._read_budget.get(_budget_key, 0)

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as _f:
            for i, line in enumerate(_f, 1):
                total += 1
                if _start <= i < _start + _limit:
                    collected.append(f"{i}|{line.rstrip()}")
                if i >= _start + _limit:
                    # Finish the loop quickly — just counting remaining lines
                    pass
            # Fast line counting trick
            for _ in _f:
                total += 1
    except (OSError, ValueError) as e:
        return json.dumps({"error": f"Error reading file: {e}"})

    # ── Smart reading: small file fully, large file first 500 lines ──
    _new_read = len(collected)
    _total_read = _already_read + _new_read
    read_file_tool._read_budget[_budget_key] = _total_read

    if total > 500 and _start <= 1:
        # Large file: show first 500 lines
        collected = collected[:500]
        result = "\n".join(collected)
        if total > 500:
            result += f"\n---\n⚠ File is {total} lines, showing first 500. Use search_files for more."
    else:
        result = "\n".join(collected)

    # Budget warning (500+ lines read)
    if _total_read > 500:
        result += f"\n---\n⚠ Read {_total_read} lines from this file. Use search_files for more."

    meta = json.dumps({
        "total_lines": total,
        "start_line": _start,
        "end_line": _start + _new_read - 1 if (_start + _new_read - 1) < total else total,
        "read_lines": _total_read,
    })
    return result + f"\n---\n{meta}"


# ─── FILE WRITE ────────────────────────────────────────────

@register_tool(
    name="write_file",
    description="Write file. Automatically creates parent directories.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
            "overwrite": {"type": "boolean", "description": "Overwrite if file exists", "default": True},
        },
        "required": ["path", "content"],
    },
    toolset="file",
)
def write_file_tool(path: str, content: str, overwrite: bool = True) -> str:
    """Write file (overwrite flag for safety)."""
    from history.file_history import file_history
    file_history.snapshot_before(path, "write_file")
    p = Path(path).expanduser()

    # Path traversal protection (early check if absolute path)
    if p.is_absolute():
        try:
            safe_resolve(str(p))
        except ValueError as e:
            return json.dumps({"error": str(e)})

    # Fix common LLM path hallucinations: /home/user → actual home
    if p.is_absolute() and str(p).startswith("/home/user"):
        p = Path(str(p).replace("/home/user", str(Path.home()), 1))

    # Only allow writing to specific directories, redirect to Desktop if not allowed
    from soul.personality import GODMODE
    if p.is_absolute() and not GODMODE:
        _allowed = [Path.home() / d for d in ("Desktop", "Documents", "Downloads", ".dorina")]
        _in_allowed = any(str(p).startswith(str(a)) for a in _allowed)
        if not _in_allowed:
            p = Path.home() / "Desktop" / p.name

    if p.exists() and not overwrite:
        return json.dumps({"error": f"File already exists: {path}. Use overwrite=true to overwrite, or try the patch tool."})

    if not p.is_absolute():
        # Default projects directory
        projects_dir = Path.home() / "Documents" / "dorina-projects"
        candidate = Path.cwd() / p
        if not candidate.parent.exists() and not candidate.exists():
            p = projects_dir / p
        else:
            p = candidate
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return json.dumps({"success": True, "path": str(p), "bytes": len(content)})


# ─── FILE SEARCH ────────────────────────────────────────────

@register_tool(
    name="search_files",
    description="Search within files (grep) or by filename.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Search pattern"},
            "path": {"type": "string", "description": "Directory (default: .)", "default": "."},
            "file_glob": {"type": "string", "description": "File filter (e.g., *.py)", "default": ""},
        },
        "required": ["pattern"],
    },
    toolset="file",
)
async def search_files_tool(pattern: str, path: str = ".", file_glob: str = "") -> str:
    import json  # local import (Python 3.14.6 intermittent GC edge-case)
    import subprocess
    import shlex
    from pathlib import Path as _Path

    # Use ripgrep if available, fallback otherwise
    has_rg = False
    try:
        await asyncio.to_thread(subprocess.run, ["rg", "--version"], capture_output=True, timeout=5)
        has_rg = True
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    # Search directories
    search_dirs = []
    raw_path = _Path(path).expanduser()
    if str(raw_path) == ".":
        dirs = [
            _Path.cwd(),
            _Path.home() / "Downloads",
            _Path.home() / "Desktop",
            _Path.home() / "Documents",
        ]
        for d in dirs:
            r = d.resolve()
            if r.exists() and r.is_dir():
                search_dirs.append(str(r))
    else:
        # Path traversal protection
        try:
            resolved = safe_resolve(str(raw_path))
        except ValueError as e:
            return json.dumps({"error": str(e)})
        search_dirs = [str(resolved)] if resolved.exists() else [str(_Path.cwd())]

    # Exclude patterns — use /** suffix to exclude directories entirely
    exclude_globs = [
        "!.venv/**", "!node_modules/**", "!__pycache__/**", "!.git/**",
        "!dist/**", "!build/**", "!.ruff_cache/**", "!.mypy_cache/**", "!*.pyc",
    ]

    if has_rg:
        # ── Ripgrep mode (fast, .gitignore-aware) ──
        # Mode 1: find by filename
        try:
            find_cmd = ["rg", "--files", "--max-depth=10", "-g", f"*{pattern}*"] + [f"-g={eg}" for eg in exclude_globs] + search_dirs
            find_result = await asyncio.to_thread(subprocess.run, find_cmd, capture_output=True, text=True, timeout=30)
            if find_result.stdout.strip():
                lines = find_result.stdout.strip().split("\n")[:30]
                return json.dumps({
                    "mode": "filename",
                    "engine": "ripgrep",
                    "matches": lines,
                    "count": len(lines),
                    "note": f"Searched for '{pattern}' in filenames (.gitignore applied)"
                }, ensure_ascii=False)
        except (subprocess.TimeoutExpired, OSError):
            pass

        # Mode 2: content search with ripgrep
        try:
            content_cmd = ["rg", "-n", "--max-count=5", "--max-depth=15"]
            if file_glob:
                content_cmd.extend(["-g", f"*.{file_glob.lstrip('*.')}"])
            for eg in exclude_globs:
                content_cmd.append(f"-g={eg}")
            content_cmd.extend([pattern] + search_dirs)
            result = await asyncio.to_thread(subprocess.run, content_cmd, capture_output=True, text=True, timeout=30)
            if result.stdout.strip():
                lines = result.stdout.strip().split("\n")[:30]
                return "\n".join(lines)
        except (subprocess.TimeoutExpired, OSError):
            pass

    else:
        # ── Fallback (Python brute-force) ──
        # Mode 1: find by name
        try:
            find_cmd = ["find"] + search_dirs + ["-maxdepth", "6", "-iname", f"*{shlex.quote(pattern)}*", "-type", "f"]
            find_result = await asyncio.to_thread(subprocess.run,
                " ".join(find_cmd) if not isinstance(find_cmd, str) else find_cmd,
                shell=True, capture_output=True, text=True, timeout=30
            )
            if find_result.stdout.strip():
                # Filter out excluded dirs
                lines = []
                for line in find_result.stdout.strip().split("\n"):
                    skip = False
                    for ex in [".venv", "node_modules", "__pycache__", ".git", "dist", "build"]:
                        if f"/{ex}/" in line or line.startswith(ex + "/"):
                            skip = True
                            break
                    if not skip:
                        lines.append(line)
                return json.dumps({
                    "mode": "filename",
                    "engine": "find",
                    "matches": lines[:20],
                    "count": len(lines),
                }, ensure_ascii=False)
        except (OSError, subprocess.TimeoutExpired):
            pass

        # Mode 2: grep content search
        all_results = {}
        for sd in search_dirs:
            try:
                cmd = ["grep", "-rn", "--max-count=5"]
                if file_glob:
                    cmd.append(f"--include={file_glob}")
                cmd.extend([pattern, sd])
                result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n")[:10]:
                        all_results[line] = True
            except (OSError, subprocess.TimeoutExpired):
                pass

        if all_results:
            lines = list(all_results.keys())[:30]
            return "\n".join(lines)

    return json.dumps({"error": "No matches found", "searched": search_dirs}, ensure_ascii=False)


# ─── FILE PATCH (find-replace) ──────────────────────────

@register_tool(
    name="patch",
    description="Find and replace in file. Single or batch. Target with start_line/end_line.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "Text to find (for single change)"},
            "new_string": {"type": "string", "description": "New text (for single change)"},
            "start_line": {"type": "integer", "description": "Search from this line only (optional)"},
            "end_line": {"type": "integer", "description": "Search up to this line only (optional)"},
            "changes": {
                "type": "array",
                "description": "For multiple changes at once: [{'old_string': 'old', 'new_string': 'new'}, ...]",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"}
                    },
                    "required": ["old_string", "new_string"]
                }
            },
            "dry_run": {"type": "boolean", "description": "Preview without making changes", "default": False},
        },
        "required": ["path"],
    },
    toolset="file",
)
def patch_tool(path: str, old_string: str = "", new_string: str = "", changes: list = None, start_line: int = None, end_line: int = None, dry_run: bool = False) -> str:
    """Find-and-replace in file. Supports single or batch changes. Dry-run support."""
    p = Path(path).expanduser()
    # Path traversal protection — only allow cwd + user directories
    _h = Path.home()
    _allowed = [
        str(Path.cwd()),
        str(_h / "Desktop"),
        str(_h / "Documents"),
        str(_h / "Downloads"),
        str(_h / ".dorina"),
        "/tmp",
    ]
    try:
        p = safe_resolve(str(p), _allowed)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    if not p.exists():
        return json.dumps({"error": f"File not found: {path}"})

    try:
        content = p.read_text(encoding="utf-8", errors="ignore")

        ops = []
        if changes:
            ops.extend(changes)
        if old_string:
            ops.append({"old_string": old_string, "new_string": new_string})

        if not ops:
            return json.dumps({"error": "No changes specified (old_string or changes required)."})

        total_count = 0
        new_content = content
        preview_lines = []

        for op in ops:
            old_str = op.get("old_string", "")
            new_str = op.get("new_string", "")
            if not old_str: continue

            # Constrain to line range if provided
            lines = new_content.split('\n')
            _start_idx = max(0, start_line - 1) if start_line else 0
            _end_idx = min(len(lines), end_line) if end_line else len(lines)

            target_block = '\n'.join(lines[_start_idx:_end_idx])

            count = target_block.count(old_str)
            if count == 0:
                return json.dumps({"error": f"Pattern not found in the specified range: {old_str[:50]}"})

            total_count += count

            if dry_run:
                block_lines = target_block.split('\n')
                for i, line in enumerate(block_lines):
                    if old_str in line:
                        preview_lines.append({
                            "line": _start_idx + i + 1,
                            "content": line,
                            "replacement": line.replace(old_str, new_str),
                        })

            new_block = target_block.replace(old_str, new_str)

            # Reconstruct the file content
            new_content = '\n'.join(lines[:_start_idx] + [new_block] + lines[_end_idx:]) if lines else new_block

        if dry_run:
            return json.dumps({
                "success": True,
                "path": str(p),
                "dry_run": True,
                "count": total_count,
                "preview": preview_lines[:20],
                "message": f"{total_count} changes found (dry-run — not written to file)",
            }, ensure_ascii=False)

        p.write_text(new_content, encoding="utf-8")

        # Verification: find changed lines and show ±2 context
        _old_lines = content.split("\n")
        _new_lines = new_content.split("\n")
        _verification = []
        for _i, (_ol, _nl) in enumerate(zip(_old_lines, _new_lines)):
            if _ol != _nl:
                _start = max(0, _i - 2)
                _end = min(len(_new_lines), _i + 3)
                _ctx = []
                for _j in range(_start, _end):
                    _mark = ">" if _j == _i else " "
                    _ctx.append(f"{_mark} {_j+1}|{_new_lines[_j]}")
                _verification.append({
                    "line": _i + 1,
                    "context": _ctx,
                })
        # If line counts differ (insertion/deletion), capture remaining
        if len(_new_lines) != len(_old_lines):
            for _i in range(min(len(_old_lines), len(_new_lines)), max(len(_old_lines), len(_new_lines))):
                if _i < len(_new_lines):
                    _start = max(0, _i - 2)
                    _end = min(len(_new_lines), _i + 3)
                    _ctx = []
                    for _j in range(_start, _end):
                        _mark = ">" if _j == _i else " "
                        _ctx.append(f"{_mark} {_j+1}|{_new_lines[_j]}")
                    _verification.append({
                        "line": _i + 1,
                        "context": _ctx,
                    })

        return json.dumps({
            "success": True,
            "path": str(p),
            "count": total_count,
            "changes": total_count,
            "bytes": len(new_content),
            "verification": {
                "changed_lines": _verification[:10],  # max 10 changed regions
                "summary": f"{len(_verification)} lines changed. DO NOT re-read the file to verify — verification is shown above."
            },
        })
    except (OSError, ValueError, json.JSONDecodeError) as e:
        return json.dumps({"error": str(e)})
