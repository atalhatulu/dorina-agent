"""Git tools — add, commit, diff, push, branch, status, log, reset, stash."""
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


@register_tool(
    name="git_status",
    description="Git status — calisma dizini durumunu goster (degisen, eklenen, silinen dosyalar).",
    parameters={
        "type": "object",
        "properties": {
            "short": {"type": "boolean", "description": "Kisa format (--short)", "default": True},
        },
        "required": [],
    },
    toolset="git",
)
async def git_status_tool(short: bool = True) -> str:
    try:
        cmd = ["git", "status"]
        if short:
            cmd.append("--short")
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        output = r.stdout.strip() or r.stderr.strip()
        return output[:5000] if output else "Temiz calisma dizini (degisiklik yok)."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_log",
    description="Git log — commit gecmisini goster. --oneline formati ile.",
    parameters={
        "type": "object",
        "properties": {
            "max_count": {"type": "integer", "description": "Gosterilecek commit sayisi", "default": 10},
            "branch": {"type": "string", "description": "Dal adi (opsiyonel)", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_log_tool(max_count: int = 10, branch: str = "") -> str:
    try:
        cmd = ["git", "log", "--oneline", f"--max-count={max_count}"]
        if branch:
            cmd.append(branch)
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        output = r.stdout.strip() or r.stderr.strip()
        return output[:5000] if output else "Commit gecmisi bulunamadi."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_reset",
    description="Git reset — staged degisiklikleri kaldir veya commit'i geri al. --soft ve --hard destegi.",
    parameters={
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "Sifirlama modu: soft (sadece HEAD), mixed (unstaged), hard (tamamen sil)", "default": "mixed"},
            "target": {"type": "string", "description": "Hedef (commit hash veya HEAD~N). Bos birakilirsa HEAD'e resetler.", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_reset_tool(mode: str = "mixed", target: str = "") -> str:
    try:
        valid_modes = {"soft", "mixed", "hard"}
        if mode not in valid_modes:
            return json.dumps({"error": f"Gecersiz mod: {mode}. Secenekler: soft, mixed, hard"})
        cmd = ["git", "reset", f"--{mode}"]
        if target:
            cmd.append(target)
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Reset ({mode}) basarili" + (f" -> {target}" if target else "")})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_stash",
    description="Git stash — degisiklikleri gecici olarak kaydet/geri al. Islemler: push, pop, list, drop.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Islem: list (listele), push (kaydet), pop (geri al), drop (sil)", "default": "list"},
            "message": {"type": "string", "description": "Push islemi icin mesaj (opsiyonel)", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_stash_tool(action: str = "list", message: str = "") -> str:
    try:
        if action == "list":
            r = await asyncio.to_thread(subprocess.run, ["git", "stash", "list"], capture_output=True, text=True, timeout=30)
            output = r.stdout.strip() or r.stderr.strip()
            return output[:5000] if output else "Stash kaydi yok."
        elif action == "push":
            cmd = ["git", "stash", "push"]
            if message:
                cmd.extend(["-m", message])
            r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "Degisiklikler stash'e kaydedildi"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "pop":
            r = await asyncio.to_thread(subprocess.run, ["git", "stash", "pop"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "En son stash geri alindi"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "drop":
            r = await asyncio.to_thread(subprocess.run, ["git", "stash", "drop"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "En son stash silindi"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        return json.dumps({"error": f"Gecersiz islem: {action}. Secenekler: list, push, pop, drop"})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})
