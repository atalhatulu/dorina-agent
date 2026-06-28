"""Güvenli kod çalıştırma — Docker container."""
from __future__ import annotations
import tempfile
from pathlib import Path
from core.logger import log


class Sandbox:
    def __init__(self):
        self.available = False
        self._check_docker()

    def _check_docker(self):
        import shutil
        self.available = shutil.which("docker") is not None

    def run_python(self, code: str, timeout: int = 15) -> str:
        if not self.available:
            return "Sandbox kullanilamiyor (Docker yok)"
        try:
            import subprocess
            import uuid
            # Write code to temporary file
            tag = uuid.uuid4().hex[:8]
            src = f"/tmp/sandbox_{tag}.py"
            Path(src).write_text(code)

            # Run in Docker container
            result = subprocess.run(
                ["docker", "run", "--rm", "--network", "none",
                 "-v", f"{src}:/code/script.py",
                 "python:3.12-slim", "python", "/code/script.py"],
                capture_output=True, text=True, timeout=timeout
            )
            Path(src).unlink(missing_ok=True)

            if result.returncode == 0:
                return result.stdout.strip() or "Kod calisti (cikti yok)"
            else:
                return f"Hata: {result.stderr.strip()[:200]}"

        except subprocess.TimeoutExpired:
            return "Zaman asimi (15sn)"
        except Exception as e:
            return f"Sandbox hatasi: {e}"

    def run_command(self, cmd: str, timeout: int = 15) -> str:
        if not self.available:
            return "Sandbox kullanilamiyor (Docker yok)"
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "run", "--rm", "--network", "none",
                 "alpine:latest", "sh", "-c", cmd],
                capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                return result.stdout.strip()[:1000] or "Tamam"
            return f"Hata: {result.stderr.strip()[:200]}"
        except Exception as e:
            return f"Sandbox hatasi: {e}"


sandbox = Sandbox()
