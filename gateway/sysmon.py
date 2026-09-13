"""
Sistem metrik toplayıcı — dashboard karşılama paneli için canlı sistem verisi.

Sunduğu alanlar (/api/status.system):
    cpu_pct, ram_pct, gpu_pct, disk_pct      (0-100)
    cpu_temp_c, gpu_temp_c, ram_used_gb, ram_total_gb
    net_latency_ms, net_down_mbps, net_up_mbps
    latency_history: number[]                (sparkline için son N ölçüm)

Kısıtlı mod: herhangi bir ölçüm başarısız olursa o alan None olur — frontend
"--" gösterir, asla çökmez. psutil yoksa tümü None.
"""
from __future__ import annotations
import glob
import socket
import time
import os
from typing import Optional

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ── GPU yolları (AMD amdgpu; NVIDIA olsa nvidia-smi ayrı işlenir) ──────
def _find_amd_gpu() -> Optional[dict]:
    """AMD GPU'nun busy + temp sysfs yollarını döndürür (yoksa None)."""
    busy = None
    # Direct ve güvenli yol: /sys/class/drm/card*/device/gpu_busy_percent
    try:
        for card in glob.glob("/sys/class/drm/card*"):
            p = os.path.join(card, "device", "gpu_busy_percent")
            if os.path.exists(p):
                busy = p
                break
    except Exception:
        pass
    # temp: amdgpu hwmon'u
    temp = None
    try:
        for card in glob.glob("/sys/class/drm/card*"):
            hw_root = os.path.join(card, "device", "hwmon")
            if not os.path.isdir(hw_root):
                continue
            for hw in glob.glob(os.path.join(hw_root, "hwmon*")):
                try:
                    name_f = os.path.join(hw, "name")
                    if open(name_f).read().strip().lower() == "amdgpu":
                        temp = os.path.join(hw, "temp1_input")
                        break
                except Exception:
                    continue
            if temp:
                break
    except Exception:
        pass
    if not busy and not temp:
        return None
    return {"busy": busy, "temp": temp}


# ── Hız testi (küçük paket, kısa zaman aşımı) ──────────────────────────
def _net_latency(host: str = "1.1.1.1", port: int = 443, timeout: float = 1.2) -> Optional[float]:
    try:
        t0 = time.time()
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return round((time.time() - t0) * 1000, 1)
    except Exception:
        return None


def _net_speed() -> tuple[Optional[float], Optional[float]]:
    """Kaba indirme/yükleme hızı (Mbps). Basit: kısa süreli aktarım örneklemesi.
    Ağ kartı sayaçlarından delta'yı ölçer — gerçek trafik yoksa ~0 döner."""
    if not HAS_PSUTIL:
        return None, None
    try:
        from psutil import net_io_counters
        s0 = net_io_counters()
        t0 = time.time()
        time.sleep(0.6)
        s1 = net_io_counters()
        dt = time.time() - t0
        down_bps = (s1.bytes_recv - s0.bytes_recv) / dt
        up_bps = (s1.bytes_sent - s0.bytes_sent) / dt
        return round(down_bps * 8 / 1e6, 2), round(up_bps * 8 / 1e6, 2)
    except Exception:
        return None, None


class SystemMonitor:
    """Canlı ölçümler + sparkline için latency geçmişi tutar."""

    def __init__(self, history_len: int = 30):
        self.history: list[float] = []
        self.history_len = history_len
        self._last_cpu = 0.0

    def snapshot(self) -> dict:
        out: dict = {}
        gpu = _find_amd_gpu()

        # CPU
        if HAS_PSUTIL:
            out["cpu_pct"] = round(psutil.cpu_percent(interval=None), 1)
            vm = psutil.virtual_memory()
            out["ram_pct"] = round(vm.percent, 1)
            out["ram_used_gb"] = round(vm.used / 1e9, 1)
            out["ram_total_gb"] = round(vm.total / 1e9, 1)
            try:
                du = psutil.disk_usage("/")
                out["disk_pct"] = round(du.percent, 1)
            except Exception:
                out["disk_pct"] = None
            try:
                # CPU sıcaklığı — cihazda çoğu zaman yok, sessiz düş
                temps = psutil.sensors_temperatures()
                t = None
                for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
                    if key in temps and temps[key]:
                        t = round(temps[key][0].current, 1)
                        break
                out["cpu_temp_c"] = t
            except Exception:
                out["cpu_temp_c"] = None
        else:
            out["cpu_pct"] = out["ram_pct"] = out["disk_pct"] = out["ram_used_gb"] = None
            out["ram_total_gb"] = None

        # GPU (AMD)
        if gpu:
            try:
                out["gpu_pct"] = int(open(gpu["busy"]).read().strip()) if gpu["busy"] else None
            except Exception:
                out["gpu_pct"] = None
            try:
                out["gpu_temp_c"] = round(int(open(gpu["temp"]).read().strip()) / 1000, 1)
            except Exception:
                out["gpu_temp_c"] = None
        else:
            out["gpu_pct"] = out["gpu_temp_c"] = None

        # Ağ
        lat = _net_latency()
        out["net_latency_ms"] = lat
        if lat is not None:
            self.history.append(lat)
            if len(self.history) > self.history_len:
                self.history = self.history[-self.history_len:]
        out["latency_history"] = list(self.history)
        down, up = _net_speed()
        out["net_down_mbps"], out["net_up_mbps"] = down, up

        return out


monitor = SystemMonitor()
