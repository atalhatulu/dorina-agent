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
from pathlib import Path
from datetime import datetime

from tools.registry import register_tool


def _find_file_smart(path: str) -> Path | None:
    """Find file across CWD, Downloads, home, and broad search."""
    p = Path(path).expanduser()
    if p.exists():
        return p
    if not p.is_absolute():
        for base in [Path.cwd(), Path.home() / "Downloads", Path.home()]:
            candidate = base / p
            if candidate.exists():
                return candidate
    try:
        from tools.builtin.basic import _search_file_broad
        matches = _search_file_broad(path, limit_hits=1)
        if matches:
            return matches[0]
    except ImportError:
        pass
    return None


# ─── CLIPBOARD ───────────────────────────────

@register_tool(
    name="clipboard_copy",
    description="Metni panoya kopyala (çok satırlı destekler). Başarı/hata raporu döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Kopyalanacak metin (çok satırlı desteklenir)"},
        },
        "required": ["text"],
    },
    toolset="data",
)
def clipboard_copy_tool(text: str) -> str:
    """Metni panoya kopyala. Başarı/hata durumunu JSON olarak döndürür."""
    try:
        import pyperclip
        pyperclip.copy(text)
        line_count = len(text.splitlines())
        return json.dumps({
            "success": True,
            "method": "pyperclip",
            "chars": len(text),
            "lines": line_count,
            "message": f"{len(text)} karakter, {line_count} satır panoya kopyalandı",
        })
    except ImportError:
        # Fallback: xclip
        try:
            p = subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(),
                              capture_output=True, timeout=5)
            if p.returncode != 0:
                return json.dumps({"success": False, "error": f"xclip hatası: {p.stderr.strip()}"})
            line_count = len(text.splitlines())
            return json.dumps({
                "success": True,
                "method": "xclip",
                "chars": len(text),
                "lines": line_count,
                "message": f"{len(text)} karakter, {line_count} satır panoya kopyalandı (xclip)",
            })
        except FileNotFoundError:
            return json.dumps({"success": False, "error": "Pano kullanılamıyor — pyperclip veya xclip gerekli"})
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})


@register_tool(
    name="clipboard_paste",
    description="Panodaki metni oku (2000 karakter sınırı, aşarsa uyarı gösterir).",
    parameters={"type": "object", "properties": {}},
    toolset="data",
)
def clipboard_paste_tool() -> str:
    """Panodan oku. 2000 karakterden uzunsa truncation uyarısı ekler."""
    try:
        import pyperclip
        full = pyperclip.paste()
    except:
        try:
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                   capture_output=True, text=True, timeout=5)
            full = result.stdout if result.stdout else ""
        except:
            return json.dumps({"success": False, "error": "Pano kullanılamıyor"})

    if not full:
        return json.dumps({"success": True, "content": "", "chars": 0, "message": "Pano boş"})

    if len(full) > 2000:
        return json.dumps({
            "success": True,
            "content": full[:2000],
            "chars": len(full),
            "truncated": True,
            "truncation_notice": f"Pano {len(full)} karakter içeriyor, ilk 2000 karakter gösteriliyor.",
            "message": f"⚠️ Uyarı: Pano {len(full)} karakter, sadece ilk 2000 karakter gösteriliyor.",
        })
    return json.dumps({
        "success": True,
        "content": full,
        "chars": len(full),
        "truncated": False,
    })


# ─── TREE ────────────────────────────────────

@register_tool(
    name="tree",
    description="Klasör yapısını ağaç şeklinde göster. Dosya boyutu ve hariç tutma deseni desteği.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Başlangıç dizini", "default": "."},
            "depth": {"type": "integer", "description": "Derinlik", "default": 2},
            "show_size": {"type": "boolean", "description": "Dosya boyutlarını göster", "default": False},
            "exclude": {"type": "string", "description": "Hariç tutulacak desen (ör: node_modules,.git,__pycache__)", "default": ""},
        },
    },
    toolset="system",
)
def tree_tool(path: str = ".", depth: int = 2, show_size: bool = False, exclude: str = "") -> str:
    """Klasör ağacı göster. Dosya boyutu ve hariç tutma deseni desteği."""
    root = Path(path).expanduser().resolve()
    if not root.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {path}"})

    exclude_patterns = [p.strip() for p in exclude.split(",") if p.strip()] if exclude else []

    def _is_excluded(name: str) -> bool:
        if name.startswith(".") or name == "__pycache__":
            return True
        for pat in exclude_patterns:
            if pat in name or name == pat:
                return True
        return False

    lines = [f"📁 {root.name}/"]
    def _walk(dir_path: Path, prefix: str = "", level: int = 0):
        if level >= depth:
            return
        entries = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for i, entry in enumerate(entries):
            if _is_excluded(entry.name):
                continue
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            icon = "📁" if entry.is_dir() else "📄"
            size_str = ""
            if show_size and entry.is_file():
                try:
                    sz = entry.stat().st_size
                    if sz < 1024:
                        size_str = f" ({sz} B)"
                    elif sz < 1024**2:
                        size_str = f" ({sz/1024:.1f} KB)"
                    else:
                        size_str = f" ({sz/1024**2:.1f} MB)"
                except:
                    pass
            lines.append(f"{prefix}{connector}{icon} {entry.name}{size_str}")
            if entry.is_dir():
                ext = "    " if is_last else "│   "
                _walk(entry, prefix + ext, level + 1)

    _walk(root)
    return "\n".join(lines[:80])  # max 80 satır


# ─── DIFF ────────────────────────────────────

@register_tool(
    name="diff",
    description="İki dosya arasındaki farkı göster. Satır sayısı ve side-by-side modu destekler.",
    parameters={
        "type": "object",
        "properties": {
            "file1": {"type": "string", "description": "Birinci dosya"},
            "file2": {"type": "string", "description": "İkinci dosya"},
            "side_by_side": {"type": "boolean", "description": "Side-by-side mod (yan yana gösterim)", "default": False},
        },
        "required": ["file1", "file2"],
    },
    toolset="data",
)
def diff_tool(file1: str, file2: str, side_by_side: bool = False) -> str:
    """Unified diff veya side-by-side karşılaştırma. Satır sayısı bilgisi ekler."""
    import difflib
    try:
        f1_text = Path(file1).expanduser().read_text()
        f2_text = Path(file2).expanduser().read_text()
        f1 = f1_text.splitlines()
        f2 = f2_text.splitlines()
    except Exception as e:
        return json.dumps({"error": str(e)})

    meta = {"file1": file1, "file2": file2, "lines1": len(f1), "lines2": len(f2)}

    if side_by_side:
        # Side-by-side diff using difflib ndiff
        matcher = difflib.SequenceMatcher(None, f1, f2)
        result_lines = []
        width = 60  # column width per side
        sep = "  │  "
        header = f"{'<' + file1 + '>':<{width}}{sep}{'<' + file2 + '>':<{width}}"
        divider = "─" * width + sep + "─" * width
        result_lines.append(header)
        result_lines.append(divider)
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                for k in range(i2 - i1):
                    l1 = k + i1
                    l2 = k + j1
                    left = f" {f1[l1]:<{width-1}}"
                    right = f" {f2[l2]:<{width-1}}"
                    result_lines.append(f"{left}{sep}{right}")
            elif op == "replace":
                max_lines = max(i2 - i1, j2 - j1)
                for k in range(max_lines):
                    left_line = f1[i1 + k] if k < i2 - i1 else ""
                    right_line = f2[j1 + k] if k < j2 - j1 else ""
                    left = f"-{left_line:<{width-1}}"
                    right = f"+{right_line:<{width-1}}"
                    result_lines.append(f"{left}{sep}{right}")
            elif op == "delete":
                for k in range(i1, i2):
                    left = f"-{f1[k]:<{width-1}}"
                    right = f"{'':<{width}}"
                    result_lines.append(f"{left}{sep}{right}")
            elif op == "insert":
                for k in range(j1, j2):
                    left = f"{'':<{width}}"
                    right = f"+{f2[k]:<{width-1}}"
                    result_lines.append(f"{left}{sep}{right}")
        result = "\n".join(result_lines[:80])
        meta["mode"] = "side_by_side"
        diff_count = sum(1 for l in result_lines if l.startswith("-") or l[width:width+5].strip().startswith("+"))
        meta["diff_lines"] = diff_count
    else:
        # Unified diff
        diff = difflib.unified_diff(f1, f2, fromfile=file1, tofile=file2, lineterm="")
        diff_list = list(diff)
        meta["mode"] = "unified"
        if len(diff_list) <= 1:
            return json.dumps({**meta, "message": "Dosyalar aynı", "changed": False})
        changed = sum(1 for l in diff_list if l.startswith("+") or l.startswith("-"))
        meta["changed_lines"] = changed
        result = "\n".join(diff_list[:100])
        meta["total_diff_lines"] = len(diff_list)

    return result + "\n\n" + json.dumps(meta)


# ─── SYSTEM INFO ─────────────────────────────

@register_tool(
    name="system_info",
    description="Sistem bilgisi göster: CPU, RAM, Disk, OS, uptime, load average, GPU.",
    parameters={"type": "object", "properties": {}},
    toolset="system",
)
def system_info_tool() -> str:
    """CPU, RAM, Disk, OS, uptime, load, GPU bilgisi."""
    info = {}
    try:
        import platform
        info["os"] = f"{platform.system()} {platform.release()}"
        info["host"] = platform.node()
        info["cpu"] = platform.processor() or "?"
        # CPU cores
        info["cores"] = os.cpu_count() or "?"
        # RAM
        with open("/proc/meminfo") as f:
            for line in f:
                if "MemTotal" in line:
                    kb = int(line.split()[1])
                    info["ram"] = f"{kb // 1024 // 1024} GB"
                    break
        # Disk
        st = shutil.disk_usage("/")
        info["disk"] = f"{st.used // (1024**3)} GB / {st.total // (1024**3)} GB"
        # Python
        info["python"] = platform.python_version()
        # Uptime
        try:
            with open("/proc/uptime") as f:
                uptime_sec = float(f.read().split()[0])
                days = int(uptime_sec // 86400)
                hours = int((uptime_sec % 86400) // 3600)
                mins = int((uptime_sec % 3600) // 60)
                info["uptime"] = f"{days}g {hours}s {mins}d"
        except:
            pass
        # Load average
        try:
            with open("/proc/loadavg") as f:
                parts = f.read().split()
                info["load_1min"] = parts[0]
                info["load_5min"] = parts[1]
                info["load_15min"] = parts[2]
        except:
            pass
        # GPU info (nvidia-smi)
        try:
            gpu_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=3
            )
            if gpu_result.returncode == 0:
                gpus = [g.strip() for g in gpu_result.stdout.strip().split("\n") if g.strip()]
                if gpus:
                    info["gpu"] = gpus
        except:
            pass
    except:
        pass
    return json.dumps(info, ensure_ascii=False)


# ─── HASH ────────────────────────────────────


# ─── BACKUP ──────────────────────────────────

@register_tool(
    name="backup",
    description="Dosyayı timestamp'li yedekle (.bak veya .20260625_120000 gibi).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Yedeklenecek dosya (zorunlu)"},
            "dated": {"type": "boolean", "description": "Tarih ekle (true=adına tarih koy)", "default": False},
        },
        "required": ["path"],
    },
    toolset="system",
)
def backup_tool(path: str, dated: bool = False) -> str:
    """Dosyayı yedekle. dated=true ise adına timestamp eklenir."""
    p = Path(path).expanduser()
    if not p.exists():
        return json.dumps({"error": f"Dosya bulunamadı: {path}"})
    if dated:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = p.with_name(f"{p.stem}.{ts}{p.suffix}")
    else:
        bak = p.with_suffix(p.suffix + ".bak")
    shutil.copy2(p, bak)
    return json.dumps({
        "original": str(p),
        "backup": str(bak),
        "size": p.stat().st_size,
        "dated": dated,
    })


# ─── JSON PRETTY ─────────────────────────────

@register_tool(
    name="json_pretty",
    description="JSON metnini düzenli formatta göster. Syntax highlighting ve minify seçenekleri.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "JSON metni veya dosya yolu"},
            "syntax_highlight": {"type": "boolean", "description": "Renkli syntax highlighting göster (ANSI renk kodları)", "default": False},
            "minify": {"type": "boolean", "description": "Sıkıştırılmış (tek satır) JSON çıktısı", "default": False},
        },
        "required": ["text"],
    },
    toolset="data",
)
def json_pretty_tool(text: str, syntax_highlight: bool = False, minify: bool = False) -> str:
    """JSON'u güzel formatta göster. Syntax highlighting ve minify seçenekleri."""
    # File or direct text?
    p = Path(text)
    if p.exists():
        data = json.loads(p.read_text())
    else:
        data = json.loads(text)

    if minify:
        output = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    else:
        output = json.dumps(data, indent=2, ensure_ascii=False)

    if syntax_highlight:
        import re as _re
        # Apply ANSI colors: keys=cyan, strings=green, numbers=yellow, bool/null=magenta
        colored = output
        # Keys (string before colon) — cyan bold
        colored = _re.sub(
            r'("[^"\\]*(?:\\.[^"\\]*)*")\s*:',
            lambda m: f"\033[36;1m{m.group(1)}\033[0m:",
            colored,
        )
        # String values — green
        colored = _re.sub(
            r'(:\s*)"([^"\\]*(?:\\.[^"\\]*)*)"',
            lambda m: f"{m.group(1)}\033[32m\"{m.group(2)}\"\033[0m",
            colored,
        )
        # Numbers — yellow
        colored = _re.sub(
            r'(:\s*)(-?\d+\.?\d*(?:[eE][+-]?\d+)?)',
            lambda m: f"{m.group(1)}\033[33m{m.group(2)}\033[0m",
            colored,
        )
        # Booleans and null — magenta
        colored = _re.sub(
            r'(:\s*)(true|false|null)',
            lambda m: f"{m.group(1)}\033[35m{m.group(2)}\033[0m",
            colored,
        )
        output = colored

    return output


# ─── MARKDOWN PREVIEW ────────────────────────

@register_tool(
    name="markdown_preview",
    description="Markdown dosyasını terminalde önizle. İsteğe bağlı render modu ile derlenmiş görünüm.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": ".md dosya yolu"},
            "lines": {"type": "integer", "description": "Satır sayısı", "default": 30},
            "render": {"type": "boolean", "description": "Derlenmiş (render) görünüm: markdown syntax'ını temizler, bold/italik/ kod bloklarını terminalde gösterir", "default": False},
        },
        "required": ["path"],
    },
    toolset="data",
)
def markdown_preview_tool(path: str, lines: int = 30, render: bool = False) -> str:
    """Markdown önizle. render=True ile derlenmiş (ANSI renkli) görünüm."""
    p = Path(path).expanduser()
    if not p.exists():
        return json.dumps({"error": f"Dosya bulunamadı: {path}"})
    content = p.read_text().splitlines()[:lines]

    if render:
        import re as _re
        rendered = []
        for line in content:
            # Heading markers → [H1] [H2] etc indicator
            line = _re.sub(r'^#{1,6}\s+', lambda m: f"\033[1;36m{'#' * len(m.group().strip())}\033[0m ", line)
            # Bold: **text** or __text__
            line = _re.sub(r'\*\*(.+?)\*\*', r'\033[1m\1\033[0m', line)
            line = _re.sub(r'__(.+?)__', r'\033[1m\1\033[0m', line)
            # Italic: *text* or _text_
            line = _re.sub(r'\*(.+?)\*', r'\033[3m\1\033[0m', line)
            line = _re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\033[3m\1\033[0m', line)
            # Inline code: `code`
            line = _re.sub(r'`([^`]+)`', r'\033[48;5;236m\1\033[0m', line)
            # Links: [text](url) → text (url)
            line = _re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1 (\033[4;34m\2\033[0m)', line)
            # Horizontal rules
            line = _re.sub(r'^[-*_]{3,}\s*$', '\033[2m────────────────────────────────\033[0m', line)
            # Blockquotes
            line = _re.sub(r'^>\s?', '\033[2m┃\033[0m ', line)
            # Unordered list markers
            line = _re.sub(r'^[\s]*[-*+]\s+', '  \033[33m•\033[0m ', line)
            rendered.append(line)
        output = '\n'.join(rendered)
        output += f"\n\n\033[2m[Render edildi | {len(content)} satır gösteriliyor]\033[0m"
        return output

    return "\n".join(content)


# ─── DISK USAGE ─────────────────────────────

@register_tool(
    name="disk_usage",
    description="Klasörün disk kullanımını göster (du). İnsan-okunur mod ve en büyük 10 klasör desteği.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Klasör yolu", "default": "."},
            "depth": {"type": "integer", "description": "Derinlik", "default": 1},
            "human_readable": {"type": "boolean", "description": "İnsan-okunur boyut (K/M/G)", "default": True},
            "top": {"type": "integer", "description": "En büyük N klasör göster (0=tümü)", "default": 10},
        },
    },
    toolset="system",
)
def disk_usage_tool(path: str = ".", depth: int = 1, human_readable: bool = True, top: int = 10) -> str:
    """Disk kullanımı göster. İnsan-okunur mod ve en büyük N klasör desteği."""
    root = Path(path).expanduser()
    if not root.exists():
        return json.dumps({"error": f"Dizin bulunamadı: {path}"})
    try:
        h_flag = "-h" if human_readable else ""
        args = ["du"]
        if h_flag:
            args.append(h_flag)
        if top and top > 0:
            # For top N, sort by size descending
            args.extend(["--max-depth=0", str(root)])
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            # Get top N subdirectories
            all_items = list(root.iterdir())
            dir_sizes = []
            for item in all_items:
                if item.is_dir():
                    r = subprocess.run(
                        ["du", "-sb" if not human_readable else "-s", str(item)],
                        capture_output=True, text=True, timeout=10
                    )
                    if r.stdout.strip():
                        parts = r.stdout.strip().split(maxsplit=1)
                        try:
                            size = int(parts[0]) if not human_readable else parts[0]
                            dir_sizes.append((size, parts[1] if len(parts) > 1 else str(item)))
                        except ValueError:
                            dir_sizes.append((0, str(item)))
            if not human_readable:
                dir_sizes.sort(key=lambda x: x[0], reverse=True)
            else:
                # Parse human sizes for sorting
                def parse_size(s):
                    s = str(s).upper().strip()
                    if s.endswith("G"):
                        return float(s[:-1]) * 1024**3
                    elif s.endswith("M"):
                        return float(s[:-1]) * 1024**2
                    elif s.endswith("K"):
                        return float(s[:-1]) * 1024
                    elif s.endswith("B"):
                        return float(s[:-1])
                    return float(s)
                dir_sizes.sort(key=lambda x: parse_size(str(x[0])), reverse=True)

            limited = dir_sizes[:top]
            import shutil as _shutil
            total = _shutil.disk_usage(str(root))
            lines = [f"📁 {root}/ — En büyük {min(top, len(dir_sizes))} klasör:"]
            for size, name in limited:
                lines.append(f"  {size:>8}  {name}")
            lines.append(f"\nToplam: {root} — {total.used // (1024**3)} GB / {total.total // (1024**3)} GB kullanımda")
            return "\n".join(lines)
        else:
            args.extend([f"--max-depth={depth}", str(root)])
            result = subprocess.run(args, capture_output=True, text=True, timeout=10)
            return result.stdout.strip()[:2000] or "du kullanılamıyor"
    except Exception as e:
        return json.dumps({"error": str(e)})


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
def timer_tool(mode: str = "countdown", seconds: int = 0, label: str = "") -> str:
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
                time.sleep(0.1)
            print(f"⏱️ %50 tamamlandı ({seconds/2:.1f} sn geçti)")
            while time.time() - start < seconds:
                time.sleep(0.1)
        else:
            while time.time() - start < seconds:
                time.sleep(0.1)
            
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
