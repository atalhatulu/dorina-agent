"""Git tools — add, commit, diff, push, branch, status, log, reset, stash."""
from __future__ import annotations
import asyncio
import json
import subprocess
from pathlib import Path

from tools.registry import register_tool


@register_tool(
    name="git_add",
    description="Git add — stage files. Use '.' for all.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to add, or '.' (all)", "default": "."},
        },
        "required": [],
    },
    toolset="git",
)
async def git_add_tool(path: str = ".") -> str:
    try:
        r = await asyncio.to_thread(subprocess.run, ["git", "add", path], capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Staged: {path}"})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_commit",
    description="Git commit — save staged changes with a message.",
    parameters={
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Commit message"},
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
    description="Git diff — show staged or unstaged changes.",
    parameters={
        "type": "object",
        "properties": {
            "staged": {"type": "boolean", "description": "Show only staged files", "default": False},
            "path": {"type": "string", "description": "Specific file (optional)", "default": ""},
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
        return output[:5000] if output else "No changes."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_branch",
    description="Git branch — list, create, or delete branches.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action: list, create, delete", "default": "list"},
            "name": {"type": "string", "description": "Branch name (required for create/delete)", "default": ""},
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
                return json.dumps({"error": "Branch name required"})
            r = await asyncio.to_thread(subprocess.run, ["git", "branch", name], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": f"Branch created: {name}"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "delete":
            if not name:
                return json.dumps({"error": "Branch name required"})
            r = await asyncio.to_thread(subprocess.run, ["git", "branch", "-D", name], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": f"Branch deleted: {name}"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        return json.dumps({"error": f"Invalid action: {action}"})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_push",
    description="Git push — send commits to remote.",
    parameters={
        "type": "object",
        "properties": {
            "remote": {"type": "string", "description": "Remote name", "default": "origin"},
            "branch": {"type": "string", "description": "Branch name", "default": "main"},
        },
        "required": [],
    },
    toolset="git",
)
async def git_push_tool(remote: str = "origin", branch: str = "main") -> str:
    try:
        r = await asyncio.to_thread(subprocess.run, ["git", "push", remote, branch], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Push successful: {remote}/{branch}"})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_status",
    description="Git status — show working tree status (changed, added, deleted files).",
    parameters={
        "type": "object",
        "properties": {
            "short": {"type": "boolean", "description": "Short format (--short)", "default": True},
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
        return output[:5000] if output else "Clean working tree (no changes)."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_log",
    description="Git log — show commit history. Uses --oneline format.",
    parameters={
        "type": "object",
        "properties": {
            "max_count": {"type": "integer", "description": "Number of commits to show", "default": 10},
            "branch": {"type": "string", "description": "Branch name (optional)", "default": ""},
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
        return output[:5000] if output else "No commit history found."
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_reset",
    description="Git reset — unstage changes or revert commits. Supports --soft and --hard.",
    parameters={
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "Reset mode: soft (HEAD only), mixed (unstaged), hard (discard all)", "default": "mixed"},
            "target": {"type": "string", "description": "Target (commit hash or HEAD~N). If empty, resets to HEAD.", "default": ""},
        },
        "required": [],
    },
    toolset="git",
)
async def git_reset_tool(mode: str = "mixed", target: str = "") -> str:
    try:
        valid_modes = {"soft", "mixed", "hard"}
        if mode not in valid_modes:
            return json.dumps({"error": f"Invalid mode: {mode}. Options: soft, mixed, hard"})
        cmd = ["git", "reset", f"--{mode}"]
        if target:
            cmd.append(target)
        r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return json.dumps({"success": True, "message": f"Reset ({mode}) successful" + (f" -> {target}" if target else "")})
        return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_stash",
    description="Git stash — temporarily save/revert changes. Actions: push, pop, list, drop.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "description": "Action: list (show), push (save), pop (restore), drop (delete)", "default": "list"},
            "message": {"type": "string", "description": "Message for push action (optional)", "default": ""},
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
            return output[:5000] if output else "No stash entries."
        elif action == "push":
            cmd = ["git", "stash", "push"]
            if message:
                cmd.extend(["-m", message])
            r = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "Changes saved to stash"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "pop":
            r = await asyncio.to_thread(subprocess.run, ["git", "stash", "pop"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "Latest stash restored"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        elif action == "drop":
            r = await asyncio.to_thread(subprocess.run, ["git", "stash", "drop"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return json.dumps({"success": True, "message": "Latest stash deleted"})
            return json.dumps({"error": r.stderr.strip() or r.stdout.strip()})
        return json.dumps({"error": f"Invalid action: {action}. Options: list, push, pop, drop"})
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        return json.dumps({"error": str(e)})
