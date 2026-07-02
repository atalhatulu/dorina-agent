"""Git tools — add, commit, diff, push, branch."""
from __future__ import annotations
import asyncio
import json
import subprocess
from pathlib import Path

from tools.registry import register_tool


@register_tool(
    name="git_add",
    description="Git add — dosyalari stage ekle. Tek dosya veya tumu icin '.' kullan.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Eklenecek dosya yolu veya '.' (tumu)", "default": "."},
        },
        "required": [],
    },
    toolset="git",
)
async def git_add_tool(path: str = ".") -> str:
    try:
        r = await asyncio.to_thread(subprocess.run, ["git", "add", path], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Stage eklendi: {path}"})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_commit",
    description="Git commit — staged degisiklikleri mesajla kaydet.",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Commit mesaji"},
        },
        "required": ["message"],
    },
    toolset="git",
)
async def git_commit_tool(message: str) -> str:
    try:
        r = await asyncio.to_thread(subprocess.run, ["git", "commit", "-m", message], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Commit: {message}"})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_diff",
    description="Git diff — staged veya unstaged farklari goster.",
    parameters={
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "description": "Sadece staged dosyalari goster", "default": False},
            "path": {"type": "string", "description": "Belirli bir dosya (opsiyonel)", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_diff_tool(staged: bool = False, path: str = "") -> str:
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        if path:
            cmd.extend(["--", path])
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        output = r.stdout.strip() or r.stderr.strip()
        return output[:5000] if output else "Degisiklik yok."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_branch",
    description="Git branch — dal listele, olustur veya sil.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Islem: list, create, delete", "default": "list"},
            "name": {"type": "string", "description": "Dal adi (create/delete icin gerekli)", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_branch_tool(action: str = "list", name: str = "") -> str:
    try:
        if action == "list":
            r = await asyncio.to_thread(subprocess.run, ["git", "branch"], capture_output=True, text=True, timeout=30)
            return r.stdout.strip() or r.stderr.strip()
        elif action == "create":
            if not name:
                return json.dumps({"error": "Dal adi gerekli"})
            r = await asyncio.to_thread(subprocess.run, ["git", "branch", name], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": f"Dal olusturuldu: {name}"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "delete":
            if not name:
                return json.dumps({"error": "Dal adi gerekli"})
            r = await asyncio.to_thread(subprocess.run, ["git", "branch", "-D", name], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": f"Dal silindi: {name}"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        return json.dumps({"error": f"Gecersiz islem: {action}"})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_push",
    description="Git push — commit'leri remote'a gonder.",
    parameters={
        "type": "object",
        "properties": {
            "remote": {"type": "string", "description": "Remote adi", "default": "origin"},
            "branch": {"type": "string", "description": "Dal adi", "default": "main"},
        },
        "required": [],
    },
    toolset="git",
)
async def git_push_tool(remote: str = "origin", branch: str = "main") -> str:
    try:
        r = await asyncio.to_thread(subprocess.run, ["git", "push", remote, branch], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Push basarili: {remote}/{branch}"})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})
