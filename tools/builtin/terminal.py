"""Terminal tools — shell command execution and batch Python."""

from __future__ import annotations
import asyncio
import json
import os
import subprocess
from pathlib import Path

from tools.registry import register_tool
from core.constants import DORINA_HOME, t
from tools.security import is_destructive, redact_secrets
from core.logger import log


def _sandbox_enabled_in_config() -> bool:
    """Check if config.yaml has tools.sandbox: docker."""
    try:
        import yaml
        cfg = DORINA_HOME / "config.yaml"
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text()) or {}
            return data.get("tools", {}).get("sandbox") == "docker"
    except (yaml.YAMLError, OSError):
        pass
    return False


def _run_in_sandbox(command: str, timeout: int) -> str | None:
    """Try to run command in Docker sandbox. Returns None if sandbox unavailable."""
    try:
        from sandbox.docker import sandbox as docker_sandbox
        if not docker_sandbox.available:
            log.warning("Docker sandbox requested but Docker not available")
            return None
        return docker_sandbox.run_shell(command, timeout=timeout)
    except (ImportError, AttributeError) as e:
        log.warning(f"Sandbox unavailable: {e}")
        return None


def _run_python_in_sandbox(code: str, timeout: int) -> str | None:
    """Try to run Python code in Docker sandbox. Returns None if sandbox unavailable."""
    try:
        from sandbox.docker import sandbox as docker_sandbox
        if not docker_sandbox.available:
            log.warning("Docker sandbox requested but Docker not available")
            return None
        return docker_sandbox.run_python(code, timeout=timeout)
    except (ImportError, AttributeError) as e:
        log.warning(f"Sandbox unavailable: {e}")
        return None


# ─── TERMINAL ─────────────────────────────────────────────

@register_tool(
    name="terminal",
    description="Run shell commands. pty=True for interactive, sandbox=True for safety.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "cwd": {"type": "string", "description": "Working directory (Optional)"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 15},
            "pty": {"type": "boolean", "description": "Use PTY (pseudo-terminal). Required for interactive prompts", "default": False},
            "background": {"type": "boolean", "description": "Run in background for long-running commands. User is not blocked.", "default": False},
            "notify_on_complete": {"type": "boolean", "description": "Use with background=True. Sends notification when command completes.", "default": False},
            "sandbox": {"type": "boolean", "description": "Run in Docker container (security). Default: follows config.yaml tools.sandbox setting", "default": None},
        },
        "required": ["command"],
    },
    toolset="terminal",
)
async def terminal_tool(command: str, cwd: str = None, timeout: int = 60, pty: bool = False, background: bool = False, notify_on_complete: bool = False, sandbox: bool = None) -> str:
    """Run a shell command. Supports PTY, cwd and background execution."""
    # ── Sandbox routing ────────────────────────────────────
    if sandbox is None:
        sandbox = _sandbox_enabled_in_config()
    if sandbox:
        sandbox_result = _run_in_sandbox(command, timeout=timeout)
        if sandbox_result is not None:
            return sandbox_result
        # Sandbox unavailable — fall through to host execution

    _shell = True

    from core.mode_manager import modes
    import soul.personality as _sp
    SUDO_PWD = getattr(_sp, "SUDO_PASSWORD", None)
    HAS_SUDO = "sudo" in command.split() if command else False

    # ── Sudo password — prompt user if not set (*** masked, verified) ──
    if HAS_SUDO and not SUDO_PWD:
        try:
            import subprocess as _sp_verify, termios as _t, tty as _tty, sys as _sys
            from rich.console import Console as _Console
            _con = _Console()
            _con.print("")
            while True:
                _con.print(f"[bold yellow]{t('terminal_sudo_password')}[/]", end="")
                _fd = _sys.stdin.fileno()
                _old = _t.tcgetattr(_fd)
                _pwd = ""
                try:
                    _tty.setraw(_fd)
                    while True:
                        _ch = _sys.stdin.read(1)
                        if _ch in ("\r", "\n"):
                            _con.print("")
                            break
                        elif _ch == "\x7f":
                            if _pwd:
                                _pwd = _pwd[:-1]
                                _con.print("\b \b", end="")
                        elif _ch == "\x03":
                            raise KeyboardInterrupt
                        else:
                            _pwd += _ch
                            _con.print("*", end="")
                finally:
                    _t.tcsetattr(_fd, _t.TCSAFLUSH, _old)

                if not _pwd:
                    continue
                _proc = _sp_verify.run(
                    ["sudo", "-S", "-k", "true"],
                    input=f"{_pwd}\n".encode(),
                    capture_output=True,
                    timeout=5,
                )
                if _proc.returncode == 0:
                    _sp.SUDO_PASSWORD = _pwd
                    break
                _con.print(f"[bold red]{t('terminal_sudo_wrong')}[/]")
        except subprocess.TimeoutExpired:
            _con.print(f"[bold red]{t('terminal_sudo_timeout')}[/]")
        except (OSError, ValueError):
            pass

    # Sudo password set — add -S flag and increase timeout
    if SUDO_PWD and HAS_SUDO and " -S " not in command:
        command = command.replace("sudo", "sudo -S ", 1)
        if timeout and timeout < 3600:
            timeout = 3600

    # Add .venv/bin to PATH (for pytest etc.)
    _env = None
    _proj_root = Path(__file__).resolve().parent.parent.parent
    _venv_bin = _proj_root / ".venv" / "bin"
    if _venv_bin.exists():
        _env = os.environ.copy()
        _env["PATH"] = str(_venv_bin) + ":" + _env.get("PATH", "")

    # git push/pull engelle
    if command.strip().startswith("git push") or command.strip().startswith("git pull"):
        return json.dumps({"error": "git push/pull blocked. Only local git commands allowed."})

    if is_destructive(command):
        return json.dumps({"error": "Command blocked (destructive pattern)"})

    if not background and "sleep " in command:
        import re as _re
        _sleep_match = _re.search(r"sleep\s+(\d+(?:\.\d+)?)", command)
        _sleep_dur = float(_sleep_match.group(1)) if _sleep_match else 999
        if _sleep_dur > 3:
            return json.dumps({"error": "ATTENTION: Do NOT run long sleep (3s+) in synchronous terminal! It freezes the interface. Use 'task_create_bash' tool instead."})

    if cwd:
        cwd_path = Path(cwd).expanduser()
        if not cwd_path.exists():
            return json.dumps({"error": f"Directory not found: {cwd}"})
        cwd = str(cwd_path)

    if background:
        from tools.builtin.bg_task_tool import task_create_bash
        if cwd:
            command = f"cd {cwd} && {command}"
        return task_create_bash(command, label=command[:60], notify_on_complete=notify_on_complete)

    try:
        if pty:
            try:
                import pty as _pty
                import select as _select
                import os as _os
                import shlex as _shlex
            except ImportError:
                return json.dumps({"error": "PTY mode is not supported on Windows. Run without PTY."})
            master_fd, slave_fd = _pty.openpty()
            proc = subprocess.Popen(
                command,
                shell=True,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd,
                close_fds=True,
            )
            _os.close(slave_fd)

            import time
            output = []
            deadline = time.time() + timeout
            while proc.poll() is None:
                if time.time() > deadline:
                    proc.kill()
                    full_out = "".join(output)
                    if len(full_out) > 5000:
                        _out_path = f"/tmp/dorina_out_{int(time.time())}.txt"
                        Path(_out_path).write_text(full_out)
                        return json.dumps({"partial": True, "path": _out_path, "size": len(full_out), "preview": full_out[:200]})
                    return json.dumps({"error": f"Command timed out ({timeout}s)", "partial": full_out[:10000]})
                r, _, _ = _select.select([master_fd], [], [], 0.1)
                if r:
                    try:
                        data = _os.read(master_fd, 4096)
                        if data:
                            chunk = data.decode("utf-8", errors="replace")
                            output.append(chunk)
                            if ("[sudo] password for" in chunk.lower() or "password:" in chunk.lower()) and not getattr(proc, "_pwd_sent", False):
                                import soul.personality as _sp
                                pwd = getattr(_sp, "SUDO_PASSWORD", None)
                                chunk = "\n" + chunk.lstrip()
                                if pwd:
                                    _os.write(master_fd, (pwd + "\n").encode("utf-8"))
                                    proc._pwd_sent = True
                    except OSError:
                        break

            try:
                while True:
                    r, _, _ = _select.select([master_fd], [], [], 0)
                    if not r:
                        break
                    data = _os.read(master_fd, 4096)
                    if data:
                        output.append(data.decode("utf-8", errors="replace"))
                    else:
                        break
            except OSError:
                pass

            _os.close(master_fd)
            full = "".join(output)
            return redact_secrets(full)[:50000]
        else:
            import soul.personality as _sp
            pwd = getattr(_sp, "SUDO_PASSWORD", None)

            run_kwargs = {
                "shell": _shell,
                "capture_output": True,
                "text": True,
                "timeout": timeout,
            }

            if pwd and "sudo" in command.split():
                if " -S " not in command:
                    command = command.replace("sudo", "sudo -S", 1)
                run_kwargs["input"] = pwd + "\n"

            result = await asyncio.to_thread(subprocess.run, command, **run_kwargs)
            output = result.stdout or result.stderr
            return redact_secrets(output)[:50000]
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out ({timeout}s)"})
    except (subprocess.CalledProcessError, OSError) as e:
        return json.dumps({"error": str(e)})


# ─── BATCH PYTHON ─────────────────────────────────────────

@register_tool(
    name="batch_python",
    description="Run Python script and get output. IDEAL for multi-file operations, batch data analysis, regex scans, file content manipulation.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute. Use print() for output. Use 'with open(...)' to read/write files."},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "sandbox": {"type": "boolean", "description": "Run in Docker container. Default: follows config.yaml tools.sandbox setting", "default": None},
        },
        "required": ["code"],
    },
    toolset="file",
)
async def batch_python_tool(code: str, timeout: int = 30, sandbox: bool = None) -> str:
    """Run a Python script. For batch operations (imports, file ops, regex)."""
    if sandbox is None:
        sandbox = _sandbox_enabled_in_config()
    if sandbox:
        sandbox_result = _run_python_in_sandbox(code, timeout=timeout)
        if sandbox_result is not None:
            return sandbox_result

    import subprocess, sys, tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        f.flush()
        try:
            r = await asyncio.to_thread(subprocess.run,
                [sys.executable, f.name],
                capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            out = (r.stdout or "")[:10000]
            err = (r.stderr or "")[:2000]
            if r.returncode != 0:
                return json.dumps({"error": f"Exit code {r.returncode}", "stderr": err, "stdout": out})
            return out or "Success (no output)"
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"Timeout ({timeout}s)"})
        except (subprocess.CalledProcessError, OSError) as e:
            return json.dumps({"error": str(e)})
        finally:
            os.unlink(f.name)
