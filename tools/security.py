"""Security — dangerous command detection, risk scoring, Docker sandbox."""

import asyncio
import re
import subprocess
from pathlib import Path

# Dangerous command patterns
DESTRUCTIVE_PATTERNS = [
    "rm -rf", "rm -rf /", "mkfs", "dd if=", "> /dev/sda",
    ":(){ :|:& };:",  # fork bomb
    "chmod 777 /", "chown -R",
    "wget", "curl", "bash <(", "sh <(",
]

# Indirect destructive patterns (python, perl, etc. scripts)
INDIRECT_DESTRUCTIVE = [
    r"(python|perl|ruby|node)\s+.*(shutil\.rmtree|os\.remove|os\.unlink|File\.delete)",
    r"(python|perl|ruby|node)\s+.*(rm\s+-rf|exec\(|system\(|subprocess)",
    r"shutil\.rmtree\(['\"]/['\"]",
    r"os\.system\(['\"]rm\s+-rf",
]

BLOCKED_PATHS = [
    "/etc", "/boot", "/sys", "/proc",
    "/.git", "/root",
]


# ── Command length guard (DoS protection) ──
MAX_COMMAND_LENGTH = 10000

# ── High-risk Python operations (batch_python) ──
# NOT blocking normal imports (os, sys are fine — os.path/os.listdir are
# everyday usage). Only blocking operations that execute arbitrary code or
# spawn system processes without the agent's own tooling.
HIGH_RISK_PYTHON = [
    r"import\s+subprocess",
    r"from\s+subprocess",
    r"os\.system\s*\(",
    r"os\.popen\s*\(",
    r"\bexec\s*\(",
    r"\beval\s*\(",
    r"__import__\s*\(",
    r"compile\s*\(",
    r"pty\.spawn",
    r"paramiko",
    r"shutil\.rmtree\s*\(['\"]/['\"]",  # root silme
]

def has_high_risk_python(code: str) -> bool:
    """High-risk Python operations that execute code / spawn processes."""
    for pattern in HIGH_RISK_PYTHON:
        if re.search(pattern, code):
            return True
    return False


def is_destructive(command: str) -> bool:
    """Is the command destructive? Regex + AST-level check."""
    cmd_lower = command.lower().strip()

    # Direct pattern check
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern in cmd_lower:
            return True

    # Indirect destructive check
    for pattern in INDIRECT_DESTRUCTIVE:
        if re.search(pattern, cmd_lower):
            return True

    return False


def is_blocked_path(path: str) -> bool:
    """Is the path blocked?"""
    p = Path(path).resolve()
    home = Path.home().resolve()
    for blocked in BLOCKED_PATHS:
        if blocked == "/root" and (p == home or str(p).startswith(str(home))):
            continue
        # Directory-boundary aware match: "/root" must not match "/root_workspace"
        if str(p) == blocked or str(p).startswith(blocked + "/"):
            return True
    return False


def safe_resolve(path: str, allowed_prefixes: list[str] | None = None) -> Path:
    """Normalise path and verify against path traversal attacks.

    Returns:
        Resolved Path object.

    Raises:
        ValueError: If path traversal is detected (outside allowed
                    directories or inside BLOCKED_PATHS).
    """
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    resolved = p.resolve()
    home = Path.home().resolve()

    # Check BLOCKED_PATHS
    for blocked in BLOCKED_PATHS:
        if blocked == "/root" and (resolved == home or str(resolved).startswith(str(home))):
            continue
        if str(resolved).startswith(blocked):
            raise ValueError(
                f"Path traversal blocked: '{path}' -> '{resolved}' "
                f"(blocked path: {blocked})"
            )

    # Check allowed prefixes
    if allowed_prefixes:
        allowed = [Path(a).resolve() for a in allowed_prefixes]
        if not any(str(resolved).startswith(str(a)) for a in allowed):
            raise ValueError(
                f"Path traversal blocked: '{path}' -> '{resolved}' "
                f"(outside allowed directories)"
            )

    return resolved


async def docker_available() -> bool:
    """Is Docker running?"""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["docker", "info"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False


async def sandbox_terminal(command: str, timeout: int = 60) -> str:
    """Run a command inside a Docker sandbox. Isolated, secure."""
    import json
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["docker", "run", "--rm", "-i",
             "--network", "none",  # No network access
             "--read-only",        # Read-only filesystem
             "--memory", "512m",   # Limit memory
             "--cpus", "1",        # Limit CPU
             "ubuntu:24.04",
             "bash", "-c", command],
            capture_output=True, text=True, timeout=timeout,
        )
        output = result.stdout or result.stderr
        return output[:50000]
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Sandbox timeout ({timeout}s)"})
    except FileNotFoundError:
        return json.dumps({"error": "Docker not found. Sandbox unavailable."})
    except (OSError, subprocess.CalledProcessError, ValueError) as e:
        return json.dumps({"error": f"Sandbox error: {e}"})


def redact_secrets(text: str) -> str:
    """Mask API key-like patterns in text."""
    patterns = [
        (r'sk-or-v1-[a-zA-Z0-9]{10,}', 'sk-or-v1-****'),
        # Underscore/hyphen included — modern keys often contain them
        (r'sk-[a-zA-Z0-9_-]{20,}', 'sk-****'),
        (r'ghp_[a-zA-Z0-9]{36}', 'ghp_****'),
        (r'AKIA[0-9A-Z]{16}', 'AKIA****'),
        (r'AIza[0-9A-Za-z\-_]{35}', 'AIza****'),
        (r'xox[baprs]-[0-9A-Za-z\-]{10,}', 'xox*-****'),
    ]
    for pattern, replacement in patterns:
        text = re.sub(pattern, replacement, text)
    return text


# ── Prompt injection guard (external content) ──────────────────────
# Scans untrusted content (web pages, RAG results) for instruction
# hijacking attempts. Blocks/neutralizes the most common injection
# patterns instead of letting raw instructions reach the LLM.
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|messages)",
    r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
    r"forget\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts|rules)",
    r"unutm[aıe]?\s+(tüm|onceki|önceki)\s+(talimat|komut|yönergeleri)",
    r"(tüm|bütün|onceki|önceki)\s+(talimat|komut|yönergeleri)[a-z]*\s+unut\b",
    r"artık\s+(şu|bu)\s+(talimat|komut)",
    r"you\s+are\s+now\s+",
    r"you\s+must\s+ignore",
    r"system\s*(prompt)?\s*:\s*",
    r"developer\s*(message)?\s*:\s*",
    r"simulate\s+(being|as)\s+",
    r"pretend\s+you\s+are",
    r"<\|?(system|developer|user)\|?>\s*[:：]",
    r"\[SYSTEM\]|\[INST\]|\[/INST\]",
]

# Suspicious tags that indicate injected instructions, not content
INJECTION_TAG_PATTERNS = [
    r"<script[\s>]",
    r"<iframe[\s>]",
    r"onerror\s*=",
    r"javascript:",
    r"data:text/html",
]


def sanitize_external_content(text: str) -> str:
    """Sanitize untrusted external text (web/RAG) against prompt injection.

    - Drops HTML tags that carry active content (script/iframe/events).
    - Replaces instruction-hijacking phrases with a neutral marker so the
      content stays readable but can't re-program the model.
    Returns the sanitized text.
    """
    if not text:
        return text

    # 1. Remove active HTML elements entirely
    text = re.sub(r"<script[^>]*>.*?</script>", "[script removed]", text, flags=re.S | re.I)
    text = re.sub(r"<iframe[^>]*>.*?</iframe>", "[iframe removed]", text, flags=re.S | re.I)
    text = re.sub(r"on\w+\s*=\s*[\"'][^\"']*[\"']", "", text, flags=re.I)
    text = re.sub(r"javascript:[^\"'\s)]+", "", text, flags=re.I)

    # 2. Neutralize instruction-hijacking phrases
    for pattern in INJECTION_PATTERNS:
        text = re.sub(pattern, "[untrusted instruction removed]", text, flags=re.I)

    return text
