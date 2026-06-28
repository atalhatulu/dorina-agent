"""Docker sandbox - güvenli kod çalıştırma."""

from __future__ import annotations

from core.logger import log


class Sandbox:
    """Docker container içinde güvenli kod çalıştır."""

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
            log.info("Docker sandbox hazır")
        except Exception:
            self._ready = False

    def run_python(self, code: str, timeout: int = 30) -> dict:
        """Python kodunu güvenli container'da çalıştır."""
        if not self._ready:
            return {"error": "Docker kullanılamıyor", "output": code[:200]}

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

    def run_shell(self, command: str, timeout: int = 30) -> dict:
        """Shell komutunu container'da çalıştır."""
        if not self._ready:
            return {"error": "Docker kullanılamıyor"}

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
