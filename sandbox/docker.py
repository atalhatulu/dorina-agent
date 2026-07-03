"""Secure code execution — Docker container (subprocess-based).

Default sandbox backend. Uses the Docker CLI directly (no SDK dependency).
"""

from __future__ import annotations
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Any

from core.logger import log
from .interface import SandboxInterface


class Sandbox(SandboxInterface):
    """Sandbox implementation using ``docker run`` via subprocess."""

    def __init__(self):
        self.available = False
        self._check_docker()

    def _check_docker(self):
        import shutil
        self.available = shutil.which("docker") is not None
        if not self.available:
            log.warning("Docker not found — sandbox unavailable")

    def is_available(self) -> bool:
        return self.available

    def run_python(self, code: str, timeout: int = 30) -> str:
        """Run Python code in a sandboxed Docker container."""
        if not self.available:
            return "Sandbox unavailable (Docker not found)."

        tag = uuid.uuid4().hex[:8]
        src = Path(tempfile.gettempdir()) / f"sandbox_{tag}.py"
        try:
            src.write_text(code)
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--read-only",
                    "--memory", "256m",
                    "--cpus", "0.5",
                    "-v", f"{src}:/code/script.py:ro",
                    "python:3.12-slim",
                    "python", "/code/script.py",
                ],
                capture_output=True, text=True, timeout=timeout,
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                return output or "Code executed (no output)"
            else:
                return f"Error: {result.stderr.strip()[:300]}"

        except subprocess.TimeoutExpired:
            return f"Timeout ({timeout}s)"
        except FileNotFoundError:
            self.available = False
            return "Docker command not found"
        except OSError as e:
            return f"Sandbox error: {e}"
        finally:
            src.unlink(missing_ok=True)

    def run_shell(self, command: str, timeout: int = 30) -> str:
        """Run a shell command in a sandboxed Alpine container."""
        if not self.available:
            return "Sandbox unavailable (Docker not found)."

        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", "none",
                    "--read-only",
                    "--memory", "128m",
                    "--cpus", "0.5",
                    "alpine:latest",
                    "sh", "-c", command,
                ],
                capture_output=True, text=True, timeout=timeout,
            )

            if result.returncode == 0:
                return result.stdout.strip()[:2000] or "Done"
            return f"Error: {result.stderr.strip()[:200]}"

        except subprocess.TimeoutExpired:
            return f"Timeout ({timeout}s)"
        except FileNotFoundError:
            self.available = False
            return "Docker command not found"
        except OSError as e:
            return f"Sandbox error: {e}"


sandbox = Sandbox()
