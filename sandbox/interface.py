"""Sandbox interface — abstract base and factory.

Two implementations:
- sandbox.docker.Sandbox — subprocess-based (default, no extra deps)
- security.sandbox.Sandbox — Docker SDK (requires `docker` pip package)

Factory function resolves `config.yaml tools.sandbox` setting.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class SandboxInterface(ABC):
    """Abstract sandbox for safe code/shell execution."""

    @abstractmethod
    def run_python(self, code: str, timeout: int = 30) -> str | dict[str, Any]:
        """Run Python code in a sandboxed environment."""
        ...

    @abstractmethod
    def run_shell(self, command: str, timeout: int = 30) -> str | dict[str, Any]:
        """Run a shell command in a sandboxed environment."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the sandbox is ready to use."""
        ...


def get_sandbox(backend: str | None = None) -> SandboxInterface:
    """Factory: resolve backend from config or explicit argument.

    Args:
        backend: One of "subprocess" (default), "docker-sdk", or None (uses config).

    Returns:
        A SandboxInterface implementation instance.
    """
    if backend is None:
        try:
            from core.config import settings
            backend = settings.tools.get("sandbox", "subprocess")
        except Exception:
            backend = "subprocess"

    backend = str(backend).lower().strip()

    if backend == "docker-sdk":
        from security.sandbox import Sandbox as DockerSDKSandbox
        return DockerSDKSandbox()
    else:
        # Default: subprocess-based (sandbox/docker.py)
        from sandbox.docker import Sandbox as SubprocessSandbox
        return SubprocessSandbox()
