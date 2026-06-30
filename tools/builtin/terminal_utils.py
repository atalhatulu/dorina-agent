"""
Terminal yardımcı tool'lar — clipboard, tree, diff, system-info, hash, backup, head/tail, count, json-pretty, markdown-preview, disk-usage.
"""

from __future__ import annotations
import json
import os
import hashlib
import shutil
import subprocess
import shlex
import asyncio
from pathlib import Path
from datetime import datetime

from tools.registry import register_tool


# ─── UUID GENERATE ───────────────────────────

@register_tool(
    name="uuid_generate",
    description="UUID üret (v1, v3, v4, v5, v7). Format: standard, hex, urn, base64. Namespace/name desteği.",
    parameters={
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Üretilecek UUID sayısı (max 100)", "default": 1},
            "version": {"type": "integer", "description": "UUID versiyonu (1, 3, 4, 5, 7)", "default": 4},
            "namespace": {"type": "string", "description": "v3/v5 için namespace (DNS, URL, OID, X500)", "default": ""},
            "name": {"type": "string", "description": "v3/v5 için isim (name)", "default": ""},
            "format": {"type": "string", "description": "Çıktı formatı: standard, hex, urn, base64", "default": "standard"},
            "uppercase": {"type": "boolean", "description": "Büyük harfle göster", "default": False},
        },
    },
    toolset="data",
)
def uuid_generate_tool(count: int = 1, version: int = 4, namespace: str = "", name: str = "", format: str = "standard", uppercase: bool = False) -> str:
    """Gelişmiş UUID üretim aracı."""
    import uuid
    import time
    import base64
    import os
    
    # Count parameter validation
    if count < 1:
        return json.dumps({
            "error": f"count parametresi negatif veya sıfır olamaz: {count}. En az 1 olmalıdır.",
            "valid_range": "1 ile 100 arası",
        })
    
    original_count = count
    count = max(1, min(100, count))
    
    warnings = []
    if original_count != count:
        if original_count > 100:
            warnings.append(f"count {original_count} değeri maksimum 100'e düşürüldü.")
        if original_count < 1 and original_count != count:
            warnings.append(f"count {original_count} değeri minimum 1'e yükseltildi.")
    
    valid_versions = {1, 3, 4, 5, 7}
    if version not in valid_versions:
        return json.dumps({"error": f"Geçersiz UUID versiyonu: {version}. Desteklenen: {sorted(valid_versions)}"})

    ns_obj = None
    if version in (3, 5):
        if not name:
            return json.dumps({"error": f"v{version} için 'name' parametresi zorunlu."})
        ns_map = {
            "DNS": uuid.NAMESPACE_DNS,
            "URL": uuid.NAMESPACE_URL,
            "OID": uuid.NAMESPACE_OID,
            "X500": uuid.NAMESPACE_X500
        }
        ns_obj = ns_map.get(namespace.upper())
        if not ns_obj:
            return json.dumps({"error": f"v{version} için geçerli bir namespace gerekli (DNS, URL, OID, X500)."})

    uuids = []
    start_time = time.time()
    
    for _ in range(count):
        if version == 1:
            u = uuid.uuid1()
        elif version == 3:
            u = uuid.uuid3(ns_obj, name)
        elif version == 4:
            u = uuid.uuid4()
        elif version == 5:
            u = uuid.uuid5(ns_obj, name)
        elif version == 7:
            try:
                import uuid6
                u = uuid6.uuid7()
            except ImportError:
                # Mock uuid7
                t_ms = int(time.time() * 1000)
                t_hex = f"{t_ms:012x}"
                rnd = os.urandom(10)
                u_str = f"{t_hex[:8]}-{t_hex[8:12]}-7{rnd.hex()[:3]}-{hex(0x80 | (rnd[1] & 0x3f))[2:]}{rnd.hex()[3:5]}-{rnd.hex()[5:17]}"
                u = uuid.UUID(u_str)

        if format == "hex":
            val = u.hex
        elif format == "urn":
            val = u.urn
        elif format == "base64":
            val = base64.urlsafe_b64encode(u.bytes).decode('utf-8').rstrip('=')
        else:
            val = str(u)
            
        if uppercase and format in ("standard", "hex", "urn"):
            val = val.upper()
            
        uuids.append(val)
        
    return json.dumps({
        "count": count,
        "version": version,
        "format": format,
        "uuids": uuids,
        "generation_time_ms": round((time.time() - start_time) * 1000, 2),
        "warnings": warnings if warnings else None,
    })


# ─── TIMER ───────────────────────────────────

import threading
_TIMER_STATE = {}
_TIMER_LOCK = threading.Lock()


def _format_seconds(seconds: float) -> str:
    """Saniyeyi hh:mm:ss.ss formatına dönüştür."""
    seconds = abs(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    if hours > 0:
        return f"{hours}s {minutes:02d}d {secs:05.2f}sn"
    elif minutes > 0:
        return f"{minutes}d {secs:05.2f}sn"
    else:
        return f"{secs:.2f}sn"


@register_tool(
    name="timer",
    description="Zamanlayıcı aracı: countdown (bekleme), stopwatch (takip), lap (tur süresi).",
    parameters={
        "type": "object",
        "properties": {
            "mode": {"type": "string", "description": "Mod: countdown, stopwatch, lap", "default": "countdown"},
            "seconds": {"type": "integer", "description": "Süre (countdown için)", "default": 0},
            "label": {"type": "string", "description": "Zamanlayıcı etiketi (stopwatch/lap için)", "default": ""},
        },
    },
    toolset="system",
)
async def timer_tool(mode: str = "countdown", seconds: int = 0, label: str = "") -> str:
    """Zamanlayıcı ve kronometre özellikleri."""
    import time
    
    if mode == "countdown":
        if seconds <= 0:
            return json.dumps({
                "error": "Countdown modunda seconds parametresi pozitif olmalıdır.",
                "message": f"Geçersiz değer: {seconds}. Lütfen 1 veya daha büyük bir sayı girin.",
            })
        
        start = time.time()
        if seconds > 10:
            while time.time() - start < seconds / 2:
                await asyncio.sleep(0.1)
            print(f"⏱️ %50 tamamlandı ({seconds/2:.1f} sn geçti)")
            while time.time() - start < seconds:
                await asyncio.sleep(0.1)
        else:
            while time.time() - start < seconds:
                await asyncio.sleep(0.1)
            
        elapsed = time.time() - start
        return json.dumps({
            "mode": "countdown",
            "requested_seconds": seconds,
            "elapsed_seconds": round(elapsed, 2),
            "elapsed_formatted": _format_seconds(elapsed),
            "message": f"⏳ Zaman doldu: {_format_seconds(seconds)}",
        })
        
    elif mode == "stopwatch":
        with _TIMER_LOCK:
            now = time.time()
            _TIMER_STATE[label] = {"start": now, "last_lap": now}
            
        res = {
            "mode": "stopwatch",
            "label": label,
            "start_timestamp": now,
            "start_formatted": time.strftime("%H:%M:%S", time.localtime(now)),
            "message": f"⏱️ Kronometre '{label}' başlatıldı ({time.strftime('%H:%M:%S', time.localtime(now))}).",
        }
        if seconds > 0:
            res["expected_end_timestamp"] = now + seconds
            res["expected_end_formatted"] = time.strftime("%H:%M:%S", time.localtime(now + seconds))
            res["expected_duration"] = seconds
            res["expected_duration_formatted"] = _format_seconds(seconds)
        return json.dumps(res)
        
    elif mode == "lap":
        with _TIMER_LOCK:
            if label not in _TIMER_STATE:
                return json.dumps({"error": f"'{label}' adında aktif bir kronometre bulunamadı. Önce stopwatch modu ile bir kronometre başlatın."})
                
            now = time.time()
            state = _TIMER_STATE[label]
            total_elapsed = now - state["start"]
            lap_elapsed = now - state["last_lap"]
            state["last_lap"] = now
            
        return json.dumps({
            "mode": "lap",
            "label": label,
            "lap_time_seconds": round(lap_elapsed, 3),
            "lap_time_formatted": _format_seconds(lap_elapsed),
            "total_time_seconds": round(total_elapsed, 3),
            "total_time_formatted": _format_seconds(total_elapsed),
            "message": f"🏁 Lap kaydedildi: {_format_seconds(lap_elapsed)} (Toplam: {_format_seconds(total_elapsed)})",
        })
        
    else:
        return json.dumps({
            "error": f"Geçersiz mod: '{mode}'. Geçerli modlar: countdown, stopwatch, lap.",
            "valid_modes": ["countdown", "stopwatch", "lap"],
        })
