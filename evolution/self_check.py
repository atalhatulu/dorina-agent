"""
Self-evolving Dorina — self-improving AI Agent core.

How it works:
1. Monitors user interactions
2. Finds recurring patterns
3. Converts them into skills
4. Detects and fixes code bugs
5. Detects and adds missing tools/modules
"""

from __future__ import annotations
import json
from core.utils import safe_json_loads
import ast
import hashlib
import subprocess
import time
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

from core.logger import log
from core.event_bus import bus
from core.constants import DORINA_HOME


# ─── SELF REVIEW REMOVED — unnecessary LLM call, tests are sufficient


# Remove bare except

LEARNINGS_FILE = DORINA_HOME / "knowledge" / "learned" / "learnings.json"


def log_learning(task_type: str, what_failed: str, what_worked: str):
    """Save a learned lesson to persistent memory."""
    data = {"learnings": []}
    if LEARNINGS_FILE.exists():
        try:
            data = json.loads(LEARNINGS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            data = {"learnings": []}

    data["learnings"].append({
        "task_type": task_type,
        "what_failed": what_failed[:200],
        "what_worked": what_worked[:200],
        "timestamp": datetime.now().isoformat(),
    })

    # Keep last 100
    data["learnings"] = data["learnings"][-100:]

    LEARNINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEARNINGS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    tmp.replace(LEARNINGS_FILE)


def get_relevant_learnings(task_description: str) -> str:
    """Retrieve past lessons for similar tasks."""
    if not LEARNINGS_FILE.exists():
        return ""
    try:
        data = json.loads(LEARNINGS_FILE.read_text())
        learnings = data.get("learnings", [])
    except (json.JSONDecodeError, OSError):
        return ""

    # Simple keyword matching
    task_lower = task_description.lower()
    task_words = set(task_lower.split())

    relevant = []
    for l in learnings:
        desc_words = set(l.get("task_type", "").lower().split())
        overlap = task_words & desc_words
        if len(overlap) >= 2:
            relevant.append(f"[{l['task_type']}] Failed: {l['what_failed']} "
                          f"| Fix: {l['what_worked']}")

    if not relevant:
        return ""

    return "Past lessons:\n" + "\n".join(relevant[-5:])


async def run_review(code: str, trigger: str = "manual") -> str:
    """Self-review removed. Only trust test results."""
    return ""

# Remove bare except
class SelfEvolution:
    """Self-improving agent engine."""

    def __init__(self):
        self.basedir = Path(__file__).parent.parent
        self.learned_patterns: list[dict] = []
        self.skill_dir = self.basedir / "skills" / "learned"
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.basedir / "data" / "evolution_history.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()
        self._subscribe_events()
        # User approval callback — settable externally
        self.confirm_callback = None

    def _load_history(self):
        """Load past learnings from history file."""
        if self.history_file.exists():
            data = safe_json_loads(self.history_file, {})
            self.learned_patterns = data.get("patterns", [])

    def _save_history(self):
        """Save learnings to history file."""
        self.history_file.write_text(json.dumps({
            "patterns": self.learned_patterns[-100:],  # last 100 patterns
            "last_updated": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False))

    def _subscribe_events(self):
        """Subscribe to event bus."""
        bus.subscribe("tool:called", self._on_tool_called)

    # ─── 1. PATTERN RECOGNITION ──────────────────────────

    def _on_tool_called(self, event: str, name: str, **kw):
        """Track tool calls, find recurring patterns."""
        now = time.time()
        
        # Track last 10 calls
        if not hasattr(self, "_recent_calls"):
            self._recent_calls = []
        self._recent_calls.append({
            "tool": name,
            "time": now,
            "args": kw.get("arguments", {}),
        })
        
        # Pattern: 5+ same tool calls in last 30 seconds
        recent = [c for c in self._recent_calls if now - c["time"] < 30]
        for tool in set(c["tool"] for c in recent):
            count = sum(1 for c in recent if c["tool"] == tool)
            if count >= 5:
                self._discover_pattern(tool, count)

    def _discover_pattern(self, tool_name: str, frequency: int):
        """Turn recurring pattern into a skill."""
        pattern = {
            "tool": tool_name,
            "frequency": frequency,
            "discovered_at": datetime.now().isoformat(),
            "times_seen": 1,
        }
        
        # Was it found before?
        for p in self.learned_patterns:
            if p["tool"] == tool_name:
                p["times_seen"] += 1
                p["frequency"] = max(p["frequency"], frequency)
                self._save_history()
                return
        
        self.learned_patterns.append(pattern)
        self._save_history()
        
        # If repeating too often, auto-create skill
        if pattern["times_seen"] >= 2:
            self._auto_create_skill(tool_name)

    def _auto_create_skill(self, tool_name: str):
        """Auto-create skill for frequently used tool (with user approval)."""
        skill_path = self.skill_dir / f"auto-{tool_name}.md"
        if skill_path.exists():
            return  # Already exists

        # Ask for user approval
        if self.confirm_callback is not None:
            confirmed = self.confirm_callback(tool_name)
            if not confirmed:
                log.info(f"Skill creation cancelled (user denied): {tool_name}")
                return
        else:
            log.info(f"Skill creation requires approval: {tool_name}")
            return  # No approval callback — default to cancel
        
        skill_content = f"""---
name: auto-{tool_name}
description: Auto-learned skill — pattern for using the {tool_name} tool
author: SelfEvolution
created: {datetime.now().strftime("%Y-%m-%d %H:%M")}
---

# Auto-Learned: {tool_name}

This skill was auto-created from usage patterns.

## When to Use?

When {tool_name} tool needs to be called.

## Steps

1. Call the {tool_name} tool with appropriate parameters
2. Check the result
3. If error, try alternative parameters
"""
        skill_path.write_text(skill_content)
        log.info(f"🧠 Auto skill created: {tool_name}")

    # ─── 2. SELF-CODE AUDIT ───────────────────────────

    def scan_for_bugs(self) -> list[dict]:
        """Scan all Python files for potential bugs."""
        bugs = []
        py_files = list(self.basedir.rglob("*.py"))
        
        for f in py_files:
            if ".venv" in str(f) or "__pycache__" in str(f):
                continue
            try:
                ast.parse(f.read_text())
            except SyntaxError as e:
                bugs.append({
                    "file": str(f.relative_to(self.basedir)),
                    "type": "syntax",
                    "line": e.lineno,
                    "msg": e.msg,
                    "fixed": False,
                })
        return bugs

    def detect_dead_code(self) -> list[dict]:
        """Find unused functions."""
        dead = []
        # Simple detection: defined but never called functions
        functions = {}
        calls = set()
        
        for f in self.basedir.rglob("*.py"):
            if ".venv" in str(f) or "__pycache__" in str(f):
                continue
            try:
                tree = ast.parse(f.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef):
                        key = f"{f.stem}.{node.name}"
                        functions[key] = str(f.relative_to(self.basedir))
                    elif isinstance(node, ast.Call):
                        if hasattr(node.func, 'id'):
                            calls.add(node.func.id)
            except (SyntaxError, TypeError):
                continue
        
        for func_name, file_path in functions.items():
            fname = func_name.split(".")[-1]
            if fname not in calls and not fname.startswith("_"):
                dead.append({"function": func_name, "file": file_path})
        
        return dead[:20]  # first 20

    def suggest_improvements(self) -> list[dict]:
        """Suggest potential improvements."""
        suggestions = []
        
        # Functions used but not in tool registry
        from tools.registry import registry
        registered = {t.name for t in registry.list()}
        
        for f in self.basedir.rglob("*.py"):
            if ".venv" in str(f) or "__pycache__" in str(f):
                continue
            content = f.read_text()
            if "@register_tool" not in content:
                continue
            for line in content.split("\n"):
                if 'def ' in line and '@register_tool' in content:
                    func_name = line.split("def ")[1].split("(")[0]
                    if func_name not in registered:
                        suggestions.append({
                            "file": str(f.relative_to(self.basedir)),
                            "function": func_name,
                            "suggestion": "Not registered in tool registry",
                        })
        return suggestions

    # ─── 3. AUTO-FIX ──────────────────────────────────

    def try_fix_bug(self, bug: dict) -> bool:
        """Try to fix a bug automatically."""
        file_path = self.basedir / bug["file"]
        if not file_path.exists():
            return False
        
        content = file_path.read_text()
        lines = content.split("\n")
        
        if bug["type"] == "syntax" and bug["line"]:
            line_idx = bug["line"] - 1
            if line_idx < len(lines):
                # Simple fix: comment out the line
                lines[line_idx] = f"# FIXME: {lines[line_idx]}  # {bug['msg']}"
                file_path.write_text("\n".join(lines))
                bug["fixed"] = True
                log.info(f"🔧 Auto-fix: {bug['file']}:{bug['line']}")
                return True
        return False

    # ─── 4. PERIODIC IMPROVEMENT ──────────────────────

    def run_self_check(self) -> dict:
        """Run complete self-check."""
        log.info("🔍 Self-check starting...")
        
        result = {
            "time": datetime.now().isoformat(),
            "bugs_found": 0,
            "bugs_fixed": 0,
            "dead_functions": 0,
            "suggestions": 0,
            "skills_learned": len(self.learned_patterns),
            "total_skills": len(list(self.skill_dir.glob("*.md"))),
        }
        
        # Scan for bugs
        bugs = self.scan_for_bugs()
        result["bugs_found"] = len(bugs)
        for bug in bugs:
            if self.try_fix_bug(bug):
                result["bugs_fixed"] += 1
        
        # Scan for dead code
        dead = self.detect_dead_code()
        result["dead_functions"] = len(dead)
        
        # Improvement suggestions
        suggestions = self.suggest_improvements()
        result["suggestions"] = len(suggestions)
        
        log.info(f"✅ Self-check complete: {result}")
        return result


# Global instance
evolution = SelfEvolution()
