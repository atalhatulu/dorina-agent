"""File analytics tools — line counts, largest files, directory stats.

Registration handled by @register_tool decorators.
"""

from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool

DEFAULT_EXCLUDE = [".venv", "node_modules", "__pycache__", ".git", "dist", "build"]


def _is_excluded(p: Path, exclude: list[str]) -> bool:
    """Check if a path is inside any excluded directory."""
    for part in p.parts:
        if part in exclude:
            return True
    return False


def _collect_files(base: Path, pattern: str, exclude: list[str]) -> list[Path]:
    """Collect files matching pattern, excluding specified dirs."""
    import glob as _glob
    matches = list(base.rglob(pattern)) if "**" in pattern else list(base.glob(pattern))
    return [m for m in matches if m.is_file() and not _is_excluded(m, exclude)]


@register_tool(
    name="count_lines",
    description="Belirtilen glob pattern'ine uyan dosyaların toplam satır sayısını döndürür. "
                "Örn: count_lines('**/*.py') → {'files': 10, 'total_lines': 5420}",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (örn: '**/*.py', 'src/**/*.ts', '*.md')",
            },
            "path": {
                "type": "string",
                "description": "Başlangıç dizini (varsayılan: proje kökü)",
                "default": "",
            },
            "exclude": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Atlancak klasör isimleri (varsayılan: .venv, node_modules, __pycache__, .git, dist, build)",
                "default": [],
            },
        },
        "required": ["pattern"],
    },
    toolset="file",
)
def count_lines_tool(pattern: str, path: str = "", exclude: list[str] = None) -> str:
    """Count total lines for files matching a glob pattern."""
    base = Path(path).resolve() if path else Path.cwd()
    if not base.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {base}"})

    ex_list = exclude if exclude else DEFAULT_EXCLUDE
    matches = _collect_files(base, pattern, ex_list)

    if not matches:
        return json.dumps({"error": f"Pattern '{pattern}' için dosya bulunamadı", "files": 0, "total_lines": 0,
                           "excluded": ex_list})

    total = 0
    file_counts = []
    for m in matches:
        try:
            text = m.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n")
            total += lines
            file_counts.append({"file": str(m), "lines": lines})
        except Exception:
            file_counts.append({"file": str(m), "lines": -1})

    return json.dumps({
        "pattern": pattern,
        "files": len(matches),
        "total_lines": total,
        "average_lines": round(total / len(matches), 1) if matches else 0,
        "excluded": ex_list,
        "details": file_counts,
    }, ensure_ascii=False)


@register_tool(
    name="find_largest_files",
    description="Pattern'e uyan dosyalar arasında satır sayısına göre en büyük N dosyayı döndürür. "
                "Örn: find_largest_files('**/*.py', top_n=5)",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern (örn: '**/*.py')",
            },
            "top_n": {
                "type": "integer",
                "description": "Kaç dosya döndürüleceği",
                "default": 10,
            },
            "path": {
                "type": "string",
                "description": "Başlangıç dizini (varsayılan: proje kökü)",
                "default": "",
            },
            "exclude": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Atlancak klasör isimleri (varsayılan: .venv, node_modules, __pycache__, .git, dist, build)",
                "default": [],
            },
        },
        "required": ["pattern"],
    },
    toolset="file",
)
def find_largest_files_tool(pattern: str, top_n: int = 10, path: str = "", exclude: list[str] = None) -> str:
    """Find top N largest files by line count matching a pattern."""
    base = Path(path).resolve() if path else Path.cwd()
    if not base.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {base}"})

    ex_list = exclude if exclude else DEFAULT_EXCLUDE
    matches = _collect_files(base, pattern, ex_list)

    if not matches:
        return json.dumps({"error": f"Pattern '{pattern}' için dosya bulunamadı",
                           "excluded": ex_list})

    file_lines = []
    for m in matches:
        try:
            text = m.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n")
            size = m.stat().st_size
            file_lines.append({
                "file": str(m),
                "lines": lines,
                "bytes": size,
                "relative": str(m.relative_to(base)) if m != base else str(m),
            })
        except Exception:
            pass

    file_lines.sort(key=lambda x: x["lines"], reverse=True)
    top = file_lines[:top_n]

    return json.dumps({
        "pattern": pattern,
        "total_matches": len(matches),
        "top_n": len(top),
        "excluded": ex_list,
        "largest_files": top,
    }, ensure_ascii=False)


@register_tool(
    name="directory_stats",
    description="Bir dizinin özet istatistiklerini döndürür: toplam dosya sayısı, toplam satır, "
                "ortalama satır, en büyük 5 dosya. Örn: directory_stats('src/')",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Analiz edilecek dizin yolu",
            },
            "file_glob": {
                "type": "string",
                "description": "Sadece belirli uzantıları say (örn: '*.py', boş bırakılırsa tümü)",
                "default": "",
            },
            "exclude": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Atlancak klasör isimleri",
                "default": [],
            },
        },
        "required": ["path"],
    },
    toolset="file",
)
def directory_stats_tool(path: str, file_glob: str = "", exclude: list[str] = None) -> str:
    """Return summary stats for a directory."""
    base = Path(path).resolve()
    if not base.exists() or not base.is_dir():
        return json.dumps({"error": f"Dizin bulunamadı: {path}"})

    ex_list = exclude if exclude else DEFAULT_EXCLUDE

    if file_glob:
        all_files = list(base.rglob(file_glob))
    else:
        all_files = [f for f in base.rglob("*") if f.is_file()]

    all_files = [f for f in all_files if f.is_file() and not _is_excluded(f, ex_list)]

    if not all_files:
        return json.dumps({"error": f"Dizinde dosya bulunamadı: {path}", "excluded": ex_list})

    total_lines = 0
    file_stats = []
    for f in all_files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
            lines = text.count("\n")
            total_lines += lines
            file_stats.append({
                "file": str(f),
                "lines": lines,
                "bytes": f.stat().st_size,
            })
        except Exception:
            pass

    file_stats.sort(key=lambda x: x["lines"], reverse=True)
    top_5 = file_stats[:5]

    return json.dumps({
        "directory": str(base),
        "total_files": len(all_files),
        "total_lines": total_lines,
        "average_lines": round(total_lines / len(all_files), 1) if all_files else 0,
        "excluded": ex_list,
        "largest_5": top_5,
    }, ensure_ascii=False)
