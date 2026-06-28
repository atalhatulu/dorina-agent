"""
Gelişmiş terminal yardımcı tool'lar — archive, process, find, csv, weather, network, encode, uuid, timer, calc, convert, git.
"""

from __future__ import annotations
import json
import os
import subprocess
import shutil
import uuid
import base64
import time
import csv
import io
from pathlib import Path
from datetime import datetime

from tools.registry import register_tool


# ─── ARCHIVE ─────────────────────────────────

@register_tool(
    name="archive_create",
    description="Dosya/klasörü zip veya tar.gz olarak arşivle. Boyut ve süre bilgisi göster.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Arşivlenecek dosya/klasör (relative veya absolute)"},
            "format": {"type": "string", "description": "zip veya tar.gz", "default": "zip"},
            "output": {"type": "string", "description": "Çıktı dosya adı (opsiyonel)", "default": ""},
        },
        "required": ["source"],
    },
    toolset="data",
)
def archive_create_tool(source: str, format: str = "zip", output: str = "") -> str:
    import time
    start = time.time()
    p = Path(source).expanduser().resolve()
    if not p.exists():
        return json.dumps({"error": f"Bulunamadı: {source}"})
    src_size = sum(f.stat().st_size for f in p.rglob("*")) if p.is_dir() else p.stat().st_size
    out_name = output or p.stem
    out_path = Path.cwd() / f"{out_name}.{format}"
    try:
        shutil.make_archive(str(out_path.with_suffix("")), format.replace("tar.gz", "gztar"), p.parent, p.name)
        elapsed = time.time() - start
        out_size = out_path.stat().st_size if out_path.exists() else 0
        return json.dumps({
            "archive": str(out_path),
            "format": format,
            "source_size": src_size,
            "archive_size": out_size,
            "compression_ratio": f"{out_size/src_size:.1%}" if src_size else "?",
            "time": f"{elapsed:.1f}s",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="archive_extract",
    description="Zip/tar.gz arşivini çıkar.",
    parameters={
        "type": "object",
        "properties": {
            "archive": {"type": "string", "description": "Arşiv dosyası"},
            "dest": {"type": "string", "description": "Hedef klasör", "default": "."},
        },
        "required": ["archive"],
    },
    toolset="data",
)
def archive_extract_tool(archive: str, dest: str = ".") -> str:
    a = Path(archive).expanduser()
    d = Path(dest).expanduser()
    if not a.exists():
        return json.dumps({"error": f"Arşiv bulunamadı: {archive}"})
    d.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(str(a), str(d))
    return json.dumps({"extracted": str(d), "archive": archive})


# ─── PROCESS MANAGER ─────────────────────────

@register_tool(
    name="ps",
    description="Çalışan process'leri listele. Sıralama ve ağaç görünümü desteği.",
    parameters={
        "type": "object",
        "properties": {
            "filter": {"type": "string", "description": "İsim filtresi (opsiyonel)", "default": ""},
            "sort": {"type": "string", "description": "Sıralama: cpu, mem, pid, time (varsayılan: mem)", "default": "mem"},
            "tree": {"type": "boolean", "description": "Ağaç görünümü (ps auxf)", "default": False},
        },
    },
    toolset="system",
)
def ps_tool(filter: str = "", sort: str = "mem", tree: bool = False) -> str:
    sort_map = {
        "cpu": "-%cpu",
        "mem": "-%mem",
        "pid": "pid",
        "time": "-time",
    }
    sort_flag = sort_map.get(sort, "-%mem")
    if tree:
        cmd = ["ps", "auxf", "--sort=" + sort_flag]
    else:
        cmd = ["ps", "aux", "--sort=" + sort_flag]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    lines = result.stdout.splitlines()
    if filter:
        lines = [l for l in lines if filter.lower() in l.lower()]
    output = "\n".join(lines[:40])  # max 40 process
    return f"📊 Sıralama: {sort} | Ağaç: {'Evet' if tree else 'Hayır'}\n{output}"


@register_tool(
    name="kill",
    description="Process'i sonlandır (PID veya isim ile). Signal adı desteği: SIGTERM, SIGKILL, SIGHUP.",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "Process ID (name ile birlikte kullanılamaz)"},
            "name": {"type": "string", "description": "Process adı (pid ile birlikte kullanılamaz, pkill ile sonlandırır)"},
            "force": {"type": "boolean", "description": "Zorla sonlandır (-9)", "default": False},
            "signal_name": {"type": "string", "description": "Sinyal adı: SIGTERM, SIGKILL, SIGHUP (force ile birlikte kullanılamaz)", "default": ""},
        },
        "required": [],
    },
    toolset="system",
)
def kill_tool(pid: int = 0, name: str = "", force: bool = False, signal_name: str = "") -> str:
    import signal as _signal
    try:
        # Determine signal number and name
        if signal_name:
            sig_num = getattr(_signal, signal_name, None)
            if sig_num is None or not isinstance(sig_num, int):
                return json.dumps({"error": f"Geçersiz sinyal adı: {signal_name}. Geçerli: SIGTERM, SIGKILL, SIGHUP"})
        elif force:
            sig_num = 9  # SIGKILL
            signal_name = "SIGKILL"
        else:
            sig_num = 15  # SIGTERM
            signal_name = "SIGTERM"

        if name and not pid:
            # Kill by process name using pkill
            sig_flag = f"-{sig_num}"
            result = subprocess.run(["pkill", sig_flag, name], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return json.dumps({"error": f"Process bulunamadı: {name}", "signal": signal_name})
            return json.dumps({"killed": name, "signal": signal_name, "method": "name"})
        elif pid and pid > 0:
            os.kill(pid, sig_num)
            return json.dumps({"killed": pid, "signal": signal_name, "method": "pid"})
        else:
            return json.dumps({"error": "pid veya name parametresi gerekli"})
    except ProcessLookupError:
        return json.dumps({"error": f"Process bulunamadı: {pid}", "signal": signal_name})
    except PermissionError:
        return json.dumps({"error": f"Yetki yok: {pid}", "signal": signal_name})


# ─── FIND IN FILES ──────────────────────────

@register_tool(
    name="find_in_files",
    description="Dosyalarda metin ara (grep). Büyük/küçük harf duyarsız ve maksimum sonuç limiti destekler.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Aranacak metin/desen"},
            "path": {"type": "string", "description": "Arama dizini", "default": "."},
            "file_pattern": {"type": "string", "description": "Dosya filtresi (örn: *.py)", "default": ""},
            "case_insensitive": {"type": "boolean", "description": "Büyük/küçük harf duyarsız arama", "default": False},
            "max_results": {"type": "integer", "description": "Maksimum sonuç sayısı", "default": 30},
        },
        "required": ["pattern"],
    },
    toolset="data",
)
def find_in_files_tool(pattern: str, path: str = ".", file_pattern: str = "", case_insensitive: bool = False, max_results: int = 30) -> str:
    """Dosyalarda metin ara. ripgrep kullanir (varsa), .venv vb. klasörler atlanir."""
    root = Path(path).expanduser()
    if not root.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {path}"})

    exclude_globs = [
        "!.venv/**", "!node_modules/**", "!__pycache__/**", "!.git/**",
        "!dist/**", "!build/**", "!.ruff_cache/**", "!.mypy_cache/**",
    ]

    import shutil
    rg_path = shutil.which("rg")
    if rg_path:
        try:
            cmd = [rg_path, "-n", "--max-count=5", "--max-depth=15"]
            if case_insensitive:
                cmd.append("-i")
            if file_pattern:
                cmd.extend(["-g", f"*.{file_pattern.lstrip('*.')}"])
            for eg in exclude_globs:
                cmd.extend(["-g", eg])
            cmd.extend([pattern, str(root)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout.strip():
                lines = result.stdout.strip().split("\n")[:max_results]
                return "\n".join(lines)
        except:
            pass

    # Fallback: plain grep
    try:
        cmd = ["grep", "-rn"]
        if case_insensitive:
            cmd.append("-i")
        if file_pattern:
            cmd.append(f"--include={file_pattern}")
        cmd.extend([pattern, str(root)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        lines = result.stdout.splitlines()[:max_results]
        # Filter out excluded dirs
        filtered = []
        for line in lines:
            skip = False
            for ex in [".venv", "node_modules", "__pycache__", ".git", "dist", "build"]:
                if f"/{ex}/" in line:
                    skip = True
                    break
            if not skip:
                filtered.append(line)
        return "\n".join(filtered) if filtered else "Eşleşme bulunamadı"
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── BATCH RENAME ───────────────────────────

@register_tool(
    name="batch_rename",
    description="Dosyaları toplu yeniden adlandır. Basit metin değiştirme veya regex desteği.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Dizin"},
            "old": {"type": "string", "description": "Eski metin veya regex deseni"},
            "new": {"type": "string", "description": "Yeni metin"},
            "preview": {"type": "boolean", "description": "Sadece göster, değişiklik yapma", "default": True},
            "dry_run": {"type": "boolean", "description": "preview ile aynı (geriye uyumluluk)", "default": True},
            "use_regex": {"type": "boolean", "description": "Regex deseni kullan (old bir regex pattern)", "default": False},
        },
        "required": ["path", "old", "new"],
    },
    toolset="data",
)
def batch_rename_tool(path: str, old: str, new: str, preview: bool = True, dry_run: bool = True, use_regex: bool = False) -> str:
    import re as _re
    root = Path(path).expanduser()
    if not root.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {path}"})
    if not root.is_dir():
        return json.dumps({"error": f"Geçerli bir dizin değil: {path}"})

    # Final decision: preview preferred (new parameter), dry_run backward compatibility
    # If either preview=False or dry_run=False, real change
    is_preview = not (preview is False or dry_run is False)

    changes = []
    errors = []

    for f in sorted(root.iterdir()):
        if not f.is_file():
            continue
        try:
            if use_regex:
                # Regex modu: old bir regex pattern, new replacement string
                new_name = _re.sub(old, new, f.name)
            else:
                # Simple text replacement
                new_name = f.name.replace(old, new)

            if new_name != f.name:
                changes.append({"from": f.name, "to": new_name})
                if not is_preview:
                    f.rename(f.parent / new_name)
        except _re.error as e:
            errors.append({"file": f.name, "error": f"Geçersiz regex: {e}"})
        except Exception as e:
            errors.append({"file": f.name, "error": str(e)})

    result = {
        "changes": changes,
        "preview": is_preview,
        "count": len(changes),
    }
    if errors:
        result["errors"] = errors
    return json.dumps(result)


# ─── CSV VIEW ───────────────────────────────

@register_tool(
    name="csv_view",
    description="CSV dosyasını sütun sayısı ve düzenli tablo olarak göster.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV dosya yolu"},
            "rows": {"type": "integer", "description": "Satır sayısı", "default": 10},
        },
        "required": ["path"],
    },
    toolset="data",
)
def csv_view_tool(path: str, rows: int = 10) -> str:
    p = Path(path).expanduser()
    if not p.exists():
        return json.dumps({"error": f"Dosya bulunamadı: {path}"})
    try:
        reader = csv.reader(io.StringIO(p.read_text()))
        all_rows = list(reader)
        if not all_rows:
            return json.dumps({"error": "CSV dosyası boş"})

        num_cols = len(all_rows[0])
        display_rows = all_rows[:rows]
        num_data_rows = len(display_rows)

        # Calculate column widths (max content per column)
        col_widths = [0] * num_cols
        for row in display_rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell))

        # Ensure minimum 3-char width per column
        col_widths = [max(w, 3) for w in col_widths]

        # Build table with proper alignment
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        out_lines = [separator]
        for row_idx, row in enumerate(display_rows):
            # Pad short rows
            padded = list(row) + [""] * (num_cols - len(row))
            cells = " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(padded))
            out_lines.append(f"| {cells} |")
            if row_idx == 0:
                out_lines.append(separator)  # header separator
        out_lines.append(separator)

        # Summary line
        summary = f"Sütun sayısı: {num_cols} | Gösterilen satır: {num_data_rows}"

        return "\n".join(out_lines) + "\n" + summary
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── WEATHER ────────────────────────────────

@register_tool(
    name="weather",
    description="Hava durumu göster (ücretsiz wttr.in). Anlık durum, 3 günlük tahmin, rüzgar detayı.",
    parameters={
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "Şehir adı", "default": ""},
            "forecast": {"type": "boolean", "description": "3 günlük tahmin göster", "default": False},
            "wind": {"type": "boolean", "description": "Rüzgar hızı/yönü detayı göster", "default": False},
        },
    },
    toolset="network",
)
def weather_tool(city: str = "", forecast: bool = False, wind: bool = False) -> str:
    import httpx
    try:
        if forecast:
            # 3-day forecast (JSON format)
            url = f"https://wttr.in/{city}?format=j1" if city else "https://wttr.in/?format=j1"
            resp = httpx.get(url, timeout=10)
            data = resp.json()
            parts = [f"🌤 Hava Durumu: {city or 'Şu anki konum'}"]
            curr = data.get("current_condition", [{}])[0]
            parts.append(f"Şu an: {curr.get('weatherDesc', [{}])[0].get('value', '?')} | {curr.get('temp_C', '?')}°C | Nem: {curr.get('humidity', '?')}%")
            for day in data.get("weather", [])[:3]:
                date = day.get("date", "?")
                maxt = day.get("maxtempC", "?")
                mint = day.get("mintempC", "?")
                desc = day.get("hourly", [{}])[0].get("weatherDesc", [{}])[0].get("value", "?")
                parts.append(f"  {date}: {desc} | {mint}°C ~ {maxt}°C")
            if wind:
                parts.append(f"  Rüzgar: {curr.get('windspeedKmph', '?')} km/h | Yön: {curr.get('winddir16Point', '?')} ({curr.get('winddirDegree', '?')}°)")
            return "\n".join(parts)
        elif wind:
            # Brief mode + wind
            fmt = "%C+%t+%h+%w+%p"
            url = f"https://wttr.in/{city}?format={fmt}" if city else f"https://wttr.in/?format={fmt}"
            resp = httpx.get(url, timeout=10)
            return f"🌤 {city or 'Bulunduğum konum'}: {resp.text.strip()}"
        else:
            url = f"https://wttr.in/{city}?format=%C+%t+%h+%w" if city else "https://wttr.in/?format=%C+%t+%h+%w"
            resp = httpx.get(url, timeout=10)
            return resp.text.strip()[:200]
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── NETWORK TOOLS ──────────────────────────

@register_tool(
    name="ping",
    description="Bir adrese ping at. Zaman aşımı ve paket boyutu desteği.",
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Hedef adres (örn: google.com)"},
            "count": {"type": "integer", "description": "Ping sayısı", "default": 3},
            "timeout": {"type": "integer", "description": "Zaman aşımı saniye (varsayılan: 10)", "default": 10},
            "packet_size": {"type": "integer", "description": "Paket boyutu (bytes, varsayılan: 56)", "default": 56},
        },
        "required": ["host"],
    },
    toolset="network",
)
def ping_tool(host: str, count: int = 3, timeout: int = 10, packet_size: int = 56) -> str:
    try:
        cmd = ["ping", "-c", str(count), "-s", str(packet_size), "-W", str(timeout), host]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5)
        return result.stdout[-600:] or "Zaman aşımı"
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="dns_lookup",
    description="DNS sorgusu yap (dig/nslookup). Destek: A, AAAA, MX, TXT, CNAME.",
    parameters={
        "type": "object",
        "properties": {
            "host": {"type": "string", "description": "Sorgulanacak adres"},
            "type": {"type": "string", "description": "Sorgu türü (A, AAAA, MX, TXT, CNAME)", "default": "A"},
        },
        "required": ["host"],
    },
    toolset="network",
)
def dns_lookup_tool(host: str, type: str = "A") -> str:
    valid_types = {"A", "AAAA", "MX", "TXT", "CNAME"}
    rtype = type.upper()
    if rtype not in valid_types:
        return json.dumps({"error": f"Geçersiz sorgu türü: {type}. Desteklenen: {', '.join(sorted(valid_types))}"})
    try:
        if rtype in ("MX", "TXT"):
            # These benefit from full dig output (not +short) for clarity
            result = subprocess.run(
                ["dig", host, rtype, "+noall", "+answer"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if not output:
                return f"{rtype} kaydı bulunamadı: {host}"
            return output[:1000]
        elif rtype == "CNAME":
            result = subprocess.run(
                ["dig", "+short", host, "CNAME"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if not output:
                # Some CNAME results show in A lookup; try checking
                return f"CNAME kaydı bulunamadı: {host}"
            return output[:500]
        else:
            # A, AAAA with +short
            result = subprocess.run(
                ["dig", "+short", host, rtype],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            return output[:500] or f"{rtype} kaydı bulunamadı: {host}"
    except Exception:
        # Fallback to nslookup only for A/AAAA
        try:
            if rtype == "A":
                result = subprocess.run(
                    ["nslookup", host],
                    capture_output=True, text=True, timeout=10
                )
                return result.stdout.strip()[:500]
            else:
                # For non-A types, try dig again without +short as last resort
                result = subprocess.run(
                    ["dig", host, rtype],
                    capture_output=True, text=True, timeout=10
                )
                return result.stdout.strip()[:500] or f"Kayıt bulunamadı: {host}"
        except Exception as e:
            return json.dumps({"error": str(e)})


# ─── ENCODE/DECODE ──────────────────────────

@register_tool(
    name="base64_encode",
    description="Metni veya dosyayı base64 ile kodla. text veya file_path parametrelerinden biri verilmeli.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Kodlanacak metin (file_path ile birlikte kullanılamaz)"},
            "file_path": {"type": "string", "description": "Kodlanacak dosya yolu (text ile birlikte kullanılamaz)"},
        },
        "required": [],
    },
    toolset="data",
)
def base64_encode_tool(text: str = "", file_path: str = "") -> str:
    if text and file_path:
        return json.dumps({"error": "Sadece text veya file_path'den birini kullanın, ikisini birden değil"})
    try:
        if file_path:
            p = Path(file_path).expanduser()
            if not p.exists():
                return json.dumps({"error": f"Dosya bulunamadı: {file_path}"})
            data = p.read_bytes()
            encoded = base64.b64encode(data).decode()
            return json.dumps({
                "encoded": encoded,
                "source": "file",
                "file": file_path,
                "size_bytes": len(data),
            })
        else:
            encoded = base64.b64encode(text.encode()).decode()
            return json.dumps({
                "encoded": encoded,
                "source": "text",
                "length": len(text),
            })
    except Exception as e:
        return json.dumps({"error": f"Base64 kodlanamadı: {e}"})


@register_tool(
    name="base64_decode",
    description="Base64 kodlu metni çöz. str veya bytes çıktı formatı seçilebilir.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Çözülecek base64 metin"},
            "output_format": {"type": "string", "description": "Çıktı formatı: 'str' (metin) veya 'bytes' (hex gösterimi)", "default": "str"},
        },
        "required": ["text"],
    },
    toolset="data",
)
def base64_decode_tool(text: str, output_format: str = "str") -> str:
    import binascii
    # Input validation
    if not text or not text.strip():
        return json.dumps({"error": "Boş base64 metni"})
    try:
        decoded = base64.b64decode(text.strip(), validate=True)
    except binascii.Error as e:
        # Padding issue possible — retry with experimental fix
        try:
            padding = 4 - len(text.strip()) % 4
            if padding != 4:
                decoded = base64.b64decode(text.strip() + "=" * padding, validate=True)
            else:
                return json.dumps({"error": f"Geçersiz base64: {e}"})
        except Exception as e2:
            return json.dumps({"error": f"Base64 çözülemedi: {e2}"})
    except Exception as e:
        return json.dumps({"error": f"Base64 çözülemedi: {e}"})

    if output_format == "bytes":
        return json.dumps({
            "data": decoded.hex(),
            "format": "bytes_hex",
            "length": len(decoded),
        })
    else:
        try:
            return decoded.decode("utf-8")
        except UnicodeDecodeError:
            return json.dumps({
                "error": "UTF-8 olarak çözülemedi, bytes çıktısı için output_format='bytes' kullanın",
                "hex": decoded.hex(),
            })


# ─── UUID ───────────────────────────────────

@register_tool(
    name="uuid_generate",
    description="UUID (benzersiz kimlik) oluştur.",
    parameters={"type": "object", "properties": {"count": {"type": "integer", "description": "Adet", "default": 1}}},
    toolset="data",
)
def uuid_generate_tool(count: int = 1) -> str:
    return "\n".join(str(uuid.uuid4()) for _ in range(min(count, 10)))


# ─── TIMER ──────────────────────────────────

@register_tool(
    name="timer",
    description="Timer/geri sayım başlat. (experimental)",
    parameters={
        "type": "object",
        "properties": {
            "seconds": {"type": "integer", "description": "Saniye"},
        },
        "required": ["seconds"],
    },
    toolset="system",
)
def timer_tool(seconds: int) -> str:
    start = time.time()
    time.sleep(min(seconds, 5))  # max 5 saniye bekle
    elapsed = time.time() - start
    return f"{elapsed:.1f}s geçti"


# ─── CALCULATOR ─────────────────────────────

@register_tool(
    name="calc",
    description="Matematiksel ifade hesapla (Python eval). Destek: +, -, *, /, **, %, sqrt(), abs(), min(), max(), round(), sayılar ve parantez.",
    parameters={
        "type": "object",
        "properties": {
            "expression": {"type": "string", "description": "Matematiksel ifade (örn: 2 + 3 * 4, sqrt(16), abs(-5), min(1,2,3))"},
        },
        "required": ["expression"],
    },
    toolset="data",
)
def calc_tool(expression: str) -> str:
    import ast, operator, math as _math
    safe_ops = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
        ast.USub: operator.neg, ast.UAdd: operator.pos,
    }
    # Allowed functions
    safe_funcs = {
        "sqrt": _math.sqrt,
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
    }
    def _eval(node):
        if isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.BinOp):
            return safe_ops[type(node.op)](_eval(node.left), _eval(node.right))
        elif isinstance(node, ast.UnaryOp):
            return safe_ops[type(node.op)](_eval(node.operand))
        elif isinstance(node, ast.Call):
            func_name = node.func.id if isinstance(node.func, ast.Name) else None
            if func_name not in safe_funcs:
                raise ValueError(f"İzin verilmeyen fonksiyon: {func_name}")
            args = [_eval(a) for a in node.args]
            return safe_funcs[func_name](*args)
        elif isinstance(node, ast.Name):
            # Variable name usage — only None check (security)
            raise ValueError(f"Değişkenler desteklenmiyor: {node.id}")
        raise ValueError("Geçersiz ifade")
    try:
        if not expression or not expression.strip():
            return json.dumps({"error": "Boş ifade"})
        tree = ast.parse(expression.strip(), mode="eval")
        result = _eval(tree.body)
        # Infinity or NaN check
        if isinstance(result, float):
            if result == float("inf") or result == float("-inf"):
                return json.dumps({"error": "Sonsuz (infinity) sonuç"})
            if result != result:  # NaN kontrolü
                return json.dumps({"error": "Tanımsız (NaN) sonuç"})
        return str(result)
    except ZeroDivisionError:
        return json.dumps({"error": "Sıfıra bölme hatası"})
    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── UNIT CONVERT ───────────────────────────

@register_tool(
    name="convert",
    description="Birim dönüştür: mb/gb, km/mil, kg/lb, inch/cm, foot/meter, ounce/gram, liter/gallon, celsius/fahrenheit/kelvin.",
    parameters={
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "Değer"},
            "from_unit": {"type": "string", "description": "Kaynak birim (mb, gb, km, mil, kg, lb, inch, cm, foot, meter, ounce, gram, liter, gallon, c, f, k)"},
            "to_unit": {"type": "string", "description": "Hedef birim"},
        },
        "required": ["value", "from_unit", "to_unit"],
    },
    toolset="data",
)
def convert_tool(value: float, from_unit: str, to_unit: str) -> str:
    conversions = {
        # Data
        ("mb", "gb"): value / 1024,
        ("gb", "mb"): value * 1024,
        # Distance
        ("km", "mil"): value * 0.621371,
        ("mil", "km"): value / 0.621371,
        ("km", "meter"): value * 1000,
        ("meter", "km"): value / 1000,
        ("inch", "cm"): value * 2.54,
        ("cm", "inch"): value / 2.54,
        ("foot", "meter"): value * 0.3048,
        ("meter", "foot"): value / 0.3048,
        # Weight
        ("kg", "lb"): value * 2.20462,
        ("lb", "kg"): value / 2.20462,
        ("ounce", "gram"): value * 28.3495,
        ("gram", "ounce"): value / 28.3495,
        # Volume
        ("liter", "gallon"): value * 0.264172,
        ("gallon", "liter"): value / 0.264172,
        # Temperature
        ("c", "f"): value * 9/5 + 32,
        ("f", "c"): (value - 32) * 5/9,
        ("c", "k"): value + 273.15,
        ("k", "c"): value - 273.15,
        ("f", "k"): (value - 32) * 5/9 + 273.15,
        ("k", "f"): (value - 273.15) * 9/5 + 32,
    }
    key = (from_unit.lower().strip(), to_unit.lower().strip())
    result = conversions.get(key)
    if result is None:
        return json.dumps({"error": f"Dönüşüm desteklenmiyor: {from_unit} -> {to_unit}"})
    return json.dumps({"value": value, "from": from_unit, "to": to_unit, "result": round(result, 4)})


# ─── GIT SHORTCUTS ──────────────────────────

@register_tool(
    name="git_status",
    description="Git durumunu göster. Kısa veya detaylı mod, branch adı gösterimi.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Git reposu yolu", "default": "."},
            "mode": {"type": "string", "description": "Gösterim modu: 'short' (kısa) veya 'detail' (detaylı)", "default": "short"},
        },
    },
    toolset="git",
)
def git_status_tool(path: str = ".", mode: str = "short") -> str:
    try:
        # Get branch name
        branch_result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        branch = branch_result.stdout.strip() or "?"
        parts = [f"🌿 Branch: {branch}"]

        if mode == "detail":
            # Full git status
            result = subprocess.run(
                ["git", "-C", path, "status"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if output:
                parts.append(output[:1500])
            else:
                parts.append("Temiz (değişiklik yok)")
        else:
            # Short mode (default)
            result = subprocess.run(
                ["git", "-C", path, "status", "--short"],
                capture_output=True, text=True, timeout=10
            )
            output = result.stdout.strip()
            if output:
                parts.append(output[:1000])
            else:
                parts.append("✅ Temiz (değişiklik yok)")

        summary = ""
        if result.stdout.strip():
            lines = [l for l in result.stdout.splitlines() if l.strip()]
            modified = sum(1 for l in lines if l.startswith(" M") or l.startswith("M "))
            added = sum(1 for l in lines if l.startswith("??") or l.startswith("A "))
            parts.insert(1, f"📊 {len(lines)} değişiklik ({added} yeni, {modified} değiştirilmiş)")

        return "\n".join(parts)
    except Exception as e:
        return json.dumps({"error": str(e)})


@register_tool(
    name="git_log",
    description="Son git commit'leri göster. Yazar filtresi ve tarih aralığı desteği.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Git reposu yolu", "default": "."},
            "count": {"type": "integer", "description": "Commit sayısı", "default": 5},
            "author": {"type": "string", "description": "Yazar filtresi (opsiyonel, isim veya email)", "default": ""},
            "since": {"type": "string", "description": "Başlangıç tarihi (örn: '2024-01-01', '1 week ago', 'yesterday')", "default": ""},
            "until": {"type": "string", "description": "Bitiş tarihi (örn: '2024-12-31', 'today')", "default": ""},
        },
    },
    toolset="git",
)
def git_log_tool(path: str = ".", count: int = 5, author: str = "", since: str = "", until: str = "") -> str:
    try:
        cmd = ["git", "-C", path, "log", f"--max-count={count}", "--oneline", "--decorate"]
        if author:
            cmd.extend([f"--author={author}"])
        if since:
            cmd.extend([f"--since={since}"])
        if until:
            cmd.extend([f"--until={until}"])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        output = result.stdout.strip()
        if not output:
            return "Commit bulunamadı"
        return output[:1000]
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── CSV TO TABLE ────────────────────────────

@register_tool(
    name="csv_to_table",
    description="CSV dosyasını okuyup düzenli tablo formatında döndür.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV dosyasının yolu (relative veya absolute)"},
        },
        "required": ["path"],
    },
    toolset="data",
)
def csv_to_table_tool(path: str) -> str:
    """CSV dosyasını oku ve formatlı tablo olarak döndür."""
    p = Path(path).expanduser()
    if not p.exists():
        return json.dumps({"error": f"Dosya bulunamadı: {path}"})
    try:
        reader = csv.reader(io.StringIO(p.read_text()))
        all_rows = list(reader)
        if not all_rows:
            return json.dumps({"error": "CSV dosyası boş"})

        num_cols = len(all_rows[0])
        num_data_rows = len(all_rows) - 1  # header hariç

        # Column widths
        col_widths = [0] * num_cols
        for row in all_rows:
            for i, cell in enumerate(row):
                if i < num_cols:
                    col_widths[i] = max(col_widths[i], len(cell))
        col_widths = [max(w, 3) for w in col_widths]

        # Build table
        separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        out_lines = [separator]
        for row_idx, row in enumerate(all_rows):
            padded = list(row) + [""] * (num_cols - len(row))
            cells = " | ".join(cell.ljust(col_widths[i]) for i, cell in enumerate(padded))
            out_lines.append(f"| {cells} |")
            if row_idx == 0:
                out_lines.append(separator)
        out_lines.append(separator)

        summary = f"Sütun: {num_cols} | Satır: {num_data_rows}"
        return "\n".join(out_lines) + "\n" + summary
    except Exception as e:
        return json.dumps({"error": str(e)})
