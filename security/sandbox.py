"""Docker sandbox — Docker SDK implementation.

Alternative sandbox backend. Requires ``docker`` pip package.
Used when ``config.yaml tools.sandbox: docker-sdk``.
"""

from __future__ import annotations

from typing import Any

from core.logger import log
from sandbox.interface import SandboxInterface


class Sandbox(SandboxInterface):
    """Sandbox implementation using the Docker SDK (``docker`` pip package)."""

    def __init__(self):
        self.client = None
        self._ready = False

    def initialize(self):
        """Docker bağlantısını başlat."""
        try:
            import docker
            self.client = docker.from_env()
            self.client.ping()
            self._ready = True
            log.info("Docker SDK sandbox hazir")
        except (ImportError, ConnectionError, Exception):
            self._ready = False
            log.warning("Docker SDK sandbox kullanilamiyor")

    def is_available(self) -> bool:
        return self._ready

    def run_python(self, code: str, timeout: int = 30) -> dict[str, Any]:
        """Python kodunu güvenli container'da çalıştır."""
        if not self._ready:
            return {"error": "Docker kullanilamiyor", "output": code[:200]}

        try:
            container = self.client.containers.run(
                image="python:3.11-slim",
                command=["python", "-c", code],
                mem_limit="256m",
                cpu_period=100000,
                cpu_quota=50000,  # 0.5 CPU
                network_disabled=True,
                read_only=True,
                remove=True,
                timeout=timeout,
            )
            return {"output": container.decode("utf-8", errors="ignore")}

        except Exception as e:
            return {"error": str(e)}

    def run_shell(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Shell komutunu container'da çalıştır."""
        if not self._ready:
            return {"error": "Docker kullanilamiyor"}

        try:
            container = self.client.containers.run(
                image="alpine:latest",
                command=["/bin/sh", "-c", command],
                mem_limit="128m",
                cpu_period=100000,
                cpu_quota=50000,
                network_disabled=True,
                read_only=True,
                remove=True,
                timeout=timeout,
            )
            return {"output": container.decode("utf-8", errors="ignore")}

        except Exception as e:
            return {"error": str(e)}


sandbox = Sandbox()
