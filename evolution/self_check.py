"""
Öğrenen Dorina — Kendini geliştiren AI Agent çekirdeği.

Nasıl çalışır:
1. Kullanıcı etkileşimlerini izler
2. Tekrar eden desenleri bulur
3. Skill'e dönüştürür
4. Kod hatalarını tespit eder ve düzeltir
5. Eksik tool/modül tespit edip ekler
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


# ─── SELF REVIEW KALDIRILDI — gereksiz LLM cagrisi, sadece testler yeterli


# Remove bare except

LEARNINGS_FILE = DORINA_HOME / "knowledge" / "learned" / "learnings.json"


def log_learning(task_type: str, what_failed: str, what_worked: str):
    """Öğrenilen dersi kalıcı hafızaya kaydet."""
    data = {"learnings": []}
    if LEARNINGS_FILE.exists():
        try:
            data = json.loads(LEARNINGS_FILE.read_text())
        except Exception:
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
    """Benzer görevler için geçmiş dersleri getir."""
    if not LEARNINGS_FILE.exists():
        return ""
    try:
        data = json.loads(LEARNINGS_FILE.read_text())
        learnings = data.get("learnings", [])
    except Exception:
        return ""

    # Simple keyword matching
    task_lower = task_description.lower()
    task_words = set(task_lower.split())

    relevant = []
    for l in learnings:
        desc_words = set(l.get("task_type", "").lower().split())
        overlap = task_words & desc_words
        if len(overlap) >= 2:
            relevant.append(f"[{l['task_type']}] Basarisiz: {l['what_failed']} "
                          f"| Cozum: {l['what_worked']}")

    if not relevant:
        return ""

    return "Gecmis dersler:\n" + "\n".join(relevant[-5:])


async def run_review(code: str, trigger: str = "manual") -> str:
    """Self-review kaldirildi. Sadece test sonuclarina guven."""
    return ""

# Remove bare except
class SelfEvolution:
    """Kendini geliştiren agent motoru."""

    def __init__(self):
        self.basedir = Path(__file__).parent.parent
        self.learned_patterns: list[dict] = []
        self.skill_dir = self.basedir / "skills" / "learned"
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.basedir / "data" / "evolution_history.json"
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()
        self._subscribe_events()
        # Kullanıcı onayı callback'i — dışarıdan set edilebilir
        self.confirm_callback = None

    def _load_history(self):
        """Geçmiş öğrenmeleri yükle."""
        if self.history_file.exists():
            data = safe_json_loads(self.history_file, {})
            self.learned_patterns = data.get("patterns", [])

    def _save_history(self):
        """Öğrenmeleri kaydet."""
        self.history_file.write_text(json.dumps({
            "patterns": self.learned_patterns[-100:],  # son 100 desen
            "last_updated": datetime.now().isoformat(),
        }, indent=2, ensure_ascii=False))

    def _subscribe_events(self):
        """Event bus'e abone ol."""
        bus.subscribe("tool:called", self._on_tool_called)

    # ─── 1. DESEN TANIMA ──────────────────────────────

    def _on_tool_called(self, event: str, name: str, **kw):
        """Tool çağrılarını izle, tekrar eden desenleri bul."""
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
        """Tekrar eden deseni skill'e dönüştür."""
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
        """Sık kullanılan tool için otomatik skill oluştur (kullanıcı onayı ile)."""
        skill_path = self.skill_dir / f"auto-{tool_name}.md"
        if skill_path.exists():
            return  # Zaten var

        # Kullanıcı onayı iste
        if self.confirm_callback is not None:
            confirmed = self.confirm_callback(tool_name)
            if not confirmed:
                log.info(f"Skill olusturma iptal edildi (kullanici onayi): {tool_name}")
                return
        else:
            log.info(f"Skill olusturma icin onay gerekli: {tool_name}")
            return  # Onay callback'i yoksa varsayılan olarak iptal et
        
        skill_content = f"""---
name: auto-{tool_name}
description: Otomatik öğrenilen skill — {tool_name} tool'unu kullanma deseni
author: SelfEvolution
created: {datetime.now().strftime("%Y-%m-%d %H:%M")}
---

# Auto-Learned: {tool_name}

Bu skill, kullanım desenlerinden otomatik oluşturuldu.

## When to Use?

{tool_name} tool'unu çağırmak gerektiğinde.

## Steps

1. {tool_name} tool'unu uygun parametrelerle çağır
2. Sonucu kontrol et
3. Hata varsa alternatif parametrelerle dene
"""
        skill_path.write_text(skill_content)
        log.info(f"🧠 Otomatik skill olusturuldu: {tool_name}")

    # ─── 2. SELF-CODE AUDIT ───────────────────────────

    def scan_for_bugs(self) -> list[dict]:
        """Tüm Python dosyalarını tara, potansiyel hataları bul."""
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
        """Kullanılmayan fonksiyonları bul."""
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
        
        return dead[:20]  # ilk 20

    def suggest_improvements(self) -> list[dict]:
        """Potansiyel iyileştirmeleri öner."""
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
                            "suggestion": "Tool registry'de kayitli degil",
                        })
        return suggestions

    # ─── 3. AUTO-FIX ──────────────────────────────────

    def try_fix_bug(self, bug: dict) -> bool:
        """Bir hatayı düzeltmeyi dene."""
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
                log.info(f"🔧 Otomatik duzeltme: {bug['file']}:{bug['line']}")
                return True
        return False

    # ─── 4. PERIODIC IMPROVEMENT ───────────────────────

    def run_self_check(self) -> dict:
        """Tam kendi kendini denetleme çalıştır."""
        log.info("🔍 Kendi kendini denetleme basliyor...")
        
        result = {
            "time": datetime.now().isoformat(),
            "bugs_found": 0,
            "bugs_fixed": 0,
            "dead_functions": 0,
            "suggestions": 0,
            "skills_learned": len(self.learned_patterns),
            "total_skills": len(list(self.skill_dir.glob("*.md"))),
        }
        
        # Hata tara
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
        
        log.info(f"✅ Kendi denetim tamam: {result}")
        return result


# Global instance
evolution = SelfEvolution()
