"""Dahili tool'lar - terminal, dosya, web, kod çalıştırma."""

from __future__ import annotations
import asyncio
import subprocess
import json
import os
from pathlib import Path

from tools.registry import register_tool, registry
from core.constants import DORINA_HOME
from core.utils import safe_json_loads
from tools.security import is_destructive, redact_secrets
from core.logger import log


def _sandbox_enabled_in_config() -> bool:
    """Check if config.yaml has tools.sandbox: docker."""
    try:
        import yaml
        from pathlib import Path
        cfg = DORINA_HOME / "config.yaml"
        if cfg.exists():
            data = yaml.safe_load(cfg.read_text()) or {}
            return data.get("tools", {}).get("sandbox") == "docker"
    except Exception:
        pass
    return False


def _run_in_sandbox(command: str, timeout: int) -> str | None:
    """Try to run command in Docker sandbox. Returns None if sandbox unavailable."""
    try:
        from sandbox.docker import sandbox as docker_sandbox
        if not docker_sandbox.available:
            log.warning("Docker sandbox istek edildi ama Docker kullanilamiyor")
            return None
        return docker_sandbox.run_shell(command, timeout=timeout)
    except Exception as e:
        log.warning(f"Sandbox kullanilamadi: {e}")
        return None


def _run_python_in_sandbox(code: str, timeout: int) -> str | None:
    """Try to run Python code in Docker sandbox. Returns None if sandbox unavailable."""
    try:
        from sandbox.docker import sandbox as docker_sandbox
        if not docker_sandbox.available:
            log.warning("Docker sandbox istek edildi ama Docker kullanilamiyor")
            return None
        return docker_sandbox.run_python(code, timeout=timeout)
    except Exception as e:
        log.warning(f"Sandbox kullanilamadi: {e}")
        return None


# ─── TERMINAL ─────────────────────────────────────────────

@register_tool(
    name="terminal",
    description="Shell komutu calistir. pty=True interaktif, sandbox=True guvenli.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Çalıştırılacak komut"},
            "cwd": {"type": "string", "description": "Çalışma dizini (Opsiyonel)"},
            "timeout": {"type": "integer", "description": "Zaman aşımı (saniye)", "default": 15},
            "pty": {"type": "boolean", "description": "PTY (pseudo-terminal) kullan. Interaktif prompt'lar için gerekli", "default": False},
            "background": {"type": "boolean", "description": "Arka planda çalıştır. Uzun süren komutlar için (airodump-ng, tcpdump, ping vb). Kullanici bloke olmaz.", "default": False},
            "notify_on_complete": {"type": "boolean", "description": "background=True ile kullanilir. Komut bitince (veya ciktida pattern yakalaninca) chate bildirim gonderir. Orn: handshake bulunca haber ver.", "default": False},
            "sandbox": {"type": "boolean", "description": "Docker container'da calistir (guvenlik). Varsayilan: config.yaml tools.sandbox ayarina gore", "default": None},
        },
        "required": ["command"],
    },
    toolset="terminal",
)
async def terminal_tool(command: str, cwd: str = None, timeout: int = 60, pty: bool = False, background: bool = False, notify_on_complete: bool = False, sandbox: bool = None) -> str:
    """Shell komutu çalıştır. PTY, cwd ve background desteği."""
    # ── Sandbox routing ────────────────────────────────────
    if sandbox is None:
        sandbox = _sandbox_enabled_in_config()
    if sandbox:
        sandbox_result = _run_in_sandbox(command, timeout=timeout)
        if sandbox_result is not None:
            return sandbox_result
        # Sandbox unavailable — fall through to host execution

    import platform as _platform
    _is_win = _platform.system() == "Windows"
    _shell = not _is_win

    from core.mode_manager import modes
    import soul.personality as _sp
    SUDO_PWD = getattr(_sp, "SUDO_PASSWORD", None)
    HAS_SUDO = "sudo" in command.split() if command else False

    # ── Sudo parolasi yoksa kullanicidan sor (*** maskeli, dogrulamali) ──
    if HAS_SUDO and not SUDO_PWD:
        try:
            import subprocess as _sp_verify, termios as _t, tty as _tty, sys as _sys
            from rich.console import Console as _Console
            _con = _Console()
            _con.print("")
            while True:
                # *** maskeli input (her karakter * olarak goster)
                _con.print("[bold yellow]🔑 sudo parolası: [/]", end="")
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
                        elif _ch == "\x7f":  # backspace
                            if _pwd:
                                _pwd = _pwd[:-1]
                                _con.print("\b \b", end="")
                        elif _ch == "\x03":  # Ctrl+C
                            raise KeyboardInterrupt
                        else:
                            _pwd += _ch
                            _con.print("*", end="")
                finally:
                    _t.tcsetattr(_fd, _t.TCSAFLUSH, _old)
                
                if not _pwd:
                    continue
                # Parolayi dogrula
                _proc = _sp_verify.run(
                    ["sudo", "-S", "-k", "true"],
                    input=f"{_pwd}\n".encode(),
                    capture_output=True,
                    timeout=5,
                )
                if _proc.returncode == 0:
                    _sp.SUDO_PASSWORD = _pwd
                    break
                _con.print("[bold red]✗ Yanlış parola, tekrar dene[/]")
        except _sp_verify.TimeoutExpired:
            _con.print("[bold red]✗ Parola doğrulama zaman aşımı[/]")
        except Exception:
            pass

    # ── Auto-background KALDIRILDI ──
    # Eskiden monitor pattern'leri (airodump, tcpdump vb.) otomatik background'a atıyordu.
    # Bu mekanizma find/ls gibi basit komutları da background'a yollayıp
    # agent'in sonuçları görmesini engelliyordu.
    # LLM background istiyorsa explicit background=True parametresi geçer.
    # (Aşağıdaki satırlar silinmedi — gerekiyorsa config'den kontrol edilebilir)
    # _monitor_patterns = [...]
    # _is_monitor = ... 
    # if _is_monitor and not background and not pty:
    #     ...

    # Sudo parolasi tanimliysa -S ekle ve timeout'u artir
    if SUDO_PWD and HAS_SUDO and " -S " not in command:
        command = command.replace("sudo", "sudo -S ", 1)
        if timeout and timeout < 3600:
            timeout = 3600

    # .venv/bin PATH'e ekle (pytest vs. icin)
    _env = None
    _proj_root = Path(__file__).resolve().parent.parent.parent
    _venv_bin = _proj_root / ".venv" / "bin"
    if _venv_bin.exists():
        _env = os.environ.copy()
        _env["PATH"] = str(_venv_bin) + ":" + _env.get("PATH", "")
    
    # git push/pull engelle
    if command.strip().startswith("git push") or command.strip().startswith("git pull"):
        return json.dumps({"error": "git push/pull engellendi. Sadece local git komutlarina izin var."})
    
    if is_destructive(command):
        return json.dumps({"error": "Bu komut engellendi (destructive pattern)"})
        
    if not background and "sleep " in command:
        # Sleep < 3sn olanlara izin ver (bekleme degil, kisa gecikme)
        import re as _re
        _sleep_match = _re.search(r"sleep\s+(\d+(?:\.\d+)?)", command)
        _sleep_dur = float(_sleep_match.group(1)) if _sleep_match else 999
        if _sleep_dur > 3:
            return json.dumps({"error": "LUTFEN DIKKAT: Uzun sleep'leri (3sn+) senkron terminal'de CALISTIRMA! Arayuzu dondurursun. Bunun yerine KESINLIKLE 'task_create_bash' aracini kullan."})
        
    if cwd:
        cwd_path = Path(cwd).expanduser()
        if not cwd_path.exists():
            return json.dumps({"error": f"Dizin bulunamadi: {cwd}"})
        cwd = str(cwd_path)

    if background:
        from tools.builtin.bg_task_tool import task_create_bash
        # task_create_bash cwd destegi yoksa cd ile ekleyelim
        if cwd:
            command = f"cd {cwd} && {command}"
        return task_create_bash(command, label=command[:60], notify_on_complete=notify_on_complete)
    
    try:
        if pty:
            try:
                # PTY mode — Linux/Mac only
                import pty as _pty
                import select as _select
                import os as _os
                import shlex as _shlex
            except ImportError:
                return json.dumps({"error": "PTY mode Windows'ta desteklenmez. PTY'siz calistirin."})
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
            large_output = False
            while proc.poll() is None:
                if time.time() > deadline:
                    proc.kill()
                    # Buyuk ciktiyi dosyaya yaz, context'i sisirme
                    full_out = "".join(output)
                    if len(full_out) > 5000:
                        _out_path = f"/tmp/dorina_out_{int(time.time())}.txt"
                        Path(_out_path).write_text(full_out)
                        return json.dumps({"partial": True, "path": _out_path, "size": len(full_out), "preview": full_out[:200]})
                    return json.dumps({"error": f"Komut zaman aşımı ({timeout}s)", "partial": full_out[:10000]})
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
                                # Prompt'u yeni satira al
                                chunk = "\n" + chunk.lstrip()
                                if pwd:
                                    _os.write(master_fd, (pwd + "\n").encode("utf-8"))
                                    proc._pwd_sent = True
                    except OSError:
                        break
            
            # Read remaining
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
            # Normal mode
            import soul.personality as _sp
            pwd = getattr(_sp, "SUDO_PASSWORD", None)
            
            run_kwargs = {
                "shell": _shell,
                "capture_output": True,
                "text": True,
                "timeout": timeout,
            }

            # Sudo sifresi varsa -S ekle ve sifreyi gonder (her modda)
            if pwd and "sudo" in command.split():
                if " -S " not in command:
                    command = command.replace("sudo", "sudo -S", 1)
                run_kwargs["input"] = pwd + "\n"

            result = await asyncio.to_thread(subprocess.run, command, **run_kwargs)
            output = result.stdout or result.stderr
            return redact_secrets(output)[:50000]
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Komut zaman aşımı ({timeout}s)"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── DOSYA OKUMA ──────────────────────────────────────────

def _search_file_broad(filename: str, limit_hits: int = 5) -> list:
    """Search file across CWD, home, Downloads, Desktop, Documents."""
    from pathlib import Path as _Path
    
    # Eğer /root/... yolu verildiyse ama root yoksa, home'a çevir
    p = _Path(filename)
    if str(p).startswith("/root/") and not p.exists():
        alt = _Path(str(p).replace("/root/", str(_Path.home()) + "/", 1))
        if alt.exists():
            return [alt]
    
    dirs = [
        _Path.cwd(),
        _Path.home(),
        _Path.home() / "Downloads",
        _Path.home() / "Desktop",
        _Path.home() / "Documents",
    ]
    # Remove duplicates and non-existent dirs
    seen = set()
    search_dirs = []
    for d in dirs:
        r = d.resolve()
        if r.exists() and str(r) not in seen:
            seen.add(str(r))
            search_dirs.append(r)
    name = _Path(filename).name
    stem = _Path(filename).stem
    matches = []
    for d in search_dirs:
        for m in list(d.rglob(f"*{name}*"))[:limit_hits]:
            matches.append(m)
        if len(matches) >= limit_hits:
            break
    if len(matches) < limit_hits:
        for d in search_dirs:
            for m in list(d.rglob(f"*{stem}*"))[:limit_hits]:
                if m not in matches:
                    matches.append(m)
            if len(matches) >= limit_hits:
                break
    return matches[:limit_hits]


@register_tool(
    name="read_file",
    description="Dosya oku. offset/limit ile sayfalama.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Dosya yolu"},
            "start_line": {"type": "integer", "description": "Başlangıç satırı (1-indexed)", "default": 1},
            "end_line": {"type": "integer", "description": "Bitiş satırı (opsiyonel)"},
            "limit": {"type": "integer", "description": "Okunacak satır sayısı", "default": 500},
            "offset": {"type": "integer", "description": "Başlangıç satırı (alternatif)", "default": 1},
        },
        "required": ["path"],
    },
    toolset="file",
)
def read_file_tool(path: str, start_line: int = None, end_line: int = None, limit: int = 200, offset: int = None) -> str:
    """Read file content with line numbers, pagination, and binary protection."""
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path.cwd() / p
    if not p.exists():
        # Turkce klasor adlarini Ingilizceye cevir (Masaustu -> Desktop, Indirilenler -> Downloads, etc)
        _tr_map = {"Masaüstü": "Desktop", "Masaustu": "Desktop", "İndirilenler": "Downloads", "Indirilenler": "Downloads", "Belgeler": "Documents", "Resimler": "Pictures", "Müzik": "Music", "Video": "Videos"}
        _path_str = str(p)
        for _tr, _en in _tr_map.items():
            if _tr in _path_str:
                _fixed = Path(_path_str.replace(_tr, _en))
                if _fixed.exists():
                    p = _fixed
                    break
        else:
            # Hala bulunamadiysa _search_file_broad dene
            matches = _search_file_broad(path)
            if matches:
                p = Path(matches[0])
            else:
                return json.dumps({"error": f"File not found: {path}"})
        
    if p.is_dir():
        return json.dumps({
            "error": "Belirttiginiz yol bir KLASOR (dizin). 'read_file' sadece dosyalari okuyabilir.",
            "suggestion": "Klasor icerigini gormek icin 'terminal' araci ile 'ls -la' veya 'tree' kullanin."
        })
        
    # 1. Binary check
    try:
        with open(p, "rb") as bf:
            chunk = bf.read(1024)
            if b"\x00" in chunk:
                return json.dumps({
                    "error": "Bu dosya muhtemelen BINARY (metin degil). Okunmasi engellendi.",
                    "path": str(p),
                    "size": p.stat().st_size
                })
    except Exception as e:
        return json.dumps({"error": f"Dosya okunurken hata: {e}"})

    # Normalize parameters
    _start = start_line if start_line is not None else (offset if offset is not None else 1)
    
    if end_line is not None:
        _limit = (end_line - _start) + 1
    else:
        _limit = limit

    if _limit <= 0:
        return json.dumps({"error": "Geçersiz satır aralığı (end_line < start_line)"})
    if _limit > 2000:
        _limit = 2000 # Hard cap for safety
        
    total = 0
    collected = []
    
    # ── Per-file read budget ──
    if not hasattr(read_file_tool, "_read_budget"):
        read_file_tool._read_budget = {}
    _budget_key = str(p.resolve())
    _already_read = read_file_tool._read_budget.get(_budget_key, 0)

    try:
        with open(p, "r", encoding="utf-8", errors="replace") as _f:
            for i, line in enumerate(_f, 1):
                total += 1
                if _start <= i < _start + _limit:
                    collected.append(f"{i}|{line.rstrip()}")
                if i >= _start + _limit:
                    # Devamını sadece saymak için döngüyü hızlıca bitir
                    pass
            # Hızlı satır sayma hilesi
            for _ in _f:
                total += 1
    except Exception as e:
        return json.dumps({"error": f"Dosya okunurken hata: {e}"})
    
    # ── Akilli okuma: kucuk dosya tam, buyuk dosya ilk 500 ──
    _new_read = len(collected)
    _total_read = _already_read + _new_read
    read_file_tool._read_budget[_budget_key] = _total_read

    if total > 500 and _start <= 1:
        # Buyuk dosya: ilk 500 satiri goster
        collected = collected[:500]
        result = "\n".join(collected)
        if total > 500:
            result += f"\n---\n⚠ Dosya {total} satir, ilk 500 gosteriliyor. Devami icin search_files kullan."
    else:
        result = "\n".join(collected)

    # Budget uyarisi (500+ satir okunduysa)
    if _total_read > 500:
        result += f"\n---\n⚠ Bu dosyadan {_total_read} satir okundu. Daha fazla satir icin search_files kullan."
    
    meta = json.dumps({
        "total_lines": total, 
        "start_line": _start, 
        "end_line": _start + _new_read - 1 if (_start + _new_read - 1) < total else total,
        "read_lines": _total_read,
    })
    return result + f"\n---\n{meta}"


# ─── Dosya Yazma ──────────────────────────────────────────

@register_tool(
    name="write_file",
    description="Dosya yaz. Parent dizinleri otomatik olusturur.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
            "overwrite": {"type": "boolean", "description": "Eğer dosya mevcutsa üstüne yaz", "default": True},
        },
        "required": ["path", "content"],
    },
    toolset="file",
)
def write_file_tool(path: str, content: str, overwrite: bool = True) -> str:
    """Write file (overwrite flag for safety)."""
    from history.file_history import file_history
    file_history.snapshot_before(path, "write_file")
    p = Path(path).expanduser()
    
    # Fix common LLM path hallucinations: /home/user → actual home
    if p.is_absolute() and str(p).startswith("/home/user"):
        p = Path(str(p).replace("/home/user", str(Path.home()), 1))
    
    # Sadece belirli dizinlere yazma izni ver, degilse Desktop'a yonlendir
    from soul.personality import GODMODE
    if p.is_absolute() and not GODMODE:
        _allowed = [Path.home() / d for d in ("Desktop", "Documents", "Downloads", ".dorina")]
        _in_allowed = any(str(p).startswith(str(a)) for a in _allowed)
        if not _in_allowed:
            p = Path.home() / "Desktop" / p.name

    if p.exists() and not overwrite:
        return json.dumps({"error": f"Dosya zaten var: {path}. Üzerine yazmak için overwrite=true kullanın veya patch tool'unu deneyin."})
    
    if not p.is_absolute():
        # Default projects directory
        projects_dir = Path.home() / "Documents" / "dorina-projects"
        candidate = Path.cwd() / p
        if not candidate.parent.exists() and not candidate.exists():
            p = projects_dir / p
        else:
            p = candidate
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return json.dumps({"success": True, "path": str(p), "bytes": len(content)})


# ─── DOSYA ARA ────────────────────────────────────────────

@register_tool(
    name="search_files",
    description="Dosya icinde (grep) veya dosya adinda ara.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Aranacak desen"},
            "path": {"type": "string", "description": "Dizin (default: .)", "default": "."},
            "file_glob": {"type": "string", "description": "Dosya filtresi (orn: *.py)", "default": ""},
        },
        "required": ["pattern"],
    },
    toolset="file",
)
async def search_files_tool(pattern: str, path: str = ".", file_glob: str = "") -> str:
    import subprocess
    import shlex
    from pathlib import Path as _Path

    # Ripgrep varsa kullan, yoksa fallback
    has_rg = False
    try:
        await asyncio.to_thread(subprocess.run, ["rg", "--version"], capture_output=True, timeout=5)
        has_rg = True
    except Exception:
        pass

    # Search directories
    search_dirs = []
    raw_path = _Path(path).expanduser()
    if str(raw_path) == ".":
        dirs = [
            _Path.cwd(),
            _Path.home() / "Downloads",
            _Path.home() / "Desktop",
            _Path.home() / "Documents",
        ]
        for d in dirs:
            r = d.resolve()
            if r.exists() and r.is_dir():
                search_dirs.append(str(r))
    else:
        search_dirs = [str(raw_path.resolve())] if raw_path.exists() else [str(_Path.cwd())]

    # Exclude patterns — use /** suffix to exclude directories entirely
    exclude_globs = [
        "!.venv/**", "!node_modules/**", "!__pycache__/**", "!.git/**",
        "!dist/**", "!build/**", "!.ruff_cache/**", "!.mypy_cache/**", "!*.pyc",
    ]

    if has_rg:
        # ── Ripgrep mode (fast, .gitignore-aware) ──
        # Mode 1: find by filename
        try:
            find_cmd = ["rg", "--files", "--max-depth=10", "-g", f"*{pattern}*"] + [f"-g={eg}" for eg in exclude_globs] + search_dirs
            find_result = await asyncio.to_thread(subprocess.run, find_cmd, capture_output=True, text=True, timeout=30)
            if find_result.stdout.strip():
                lines = find_result.stdout.strip().split("\n")[:30]
                return json.dumps({
                    "mode": "filename",
                    "engine": "ripgrep",
                    "matches": lines,
                    "count": len(lines),
                    "note": f"Dosya isminde '{pattern}' arandı (.gitignore uygulandi)"
                }, ensure_ascii=False)
        except Exception:
            pass

        # Mode 2: content search with ripgrep
        try:
            content_cmd = ["rg", "-n", "--max-count=5", "--max-depth=15"]
            if file_glob:
                content_cmd.extend(["-g", f"*.{file_glob.lstrip('*.')}"])
            for eg in exclude_globs:
                content_cmd.append(f"-g={eg}")
            content_cmd.extend([pattern] + search_dirs)
            result = await asyncio.to_thread(subprocess.run, content_cmd, capture_output=True, text=True, timeout=30)
            if result.stdout.strip():
                lines = result.stdout.strip().split("\n")[:30]
                return "\n".join(lines)
        except Exception:
            pass

    else:
        # ── Fallback (Python brute-force) ──
        # Mode 1: find by name
        try:
            find_cmd = ["find"] + search_dirs + ["-maxdepth", "6", "-iname", f"*{shlex.quote(pattern)}*", "-type", "f"]
            find_result = await asyncio.to_thread(subprocess.run,
                " ".join(find_cmd) if not isinstance(find_cmd, str) else find_cmd,
                shell=True, capture_output=True, text=True, timeout=30
            )
            if find_result.stdout.strip():
                # Filter out excluded dirs
                lines = []
                for line in find_result.stdout.strip().split("\n"):
                    skip = False
                    for ex in [".venv", "node_modules", "__pycache__", ".git", "dist", "build"]:
                        if f"/{ex}/" in line or line.startswith(ex + "/"):
                            skip = True
                            break
                    if not skip:
                        lines.append(line)
                return json.dumps({
                    "mode": "filename",
                    "engine": "find",
                    "matches": lines[:20],
                    "count": len(lines),
                }, ensure_ascii=False)
        except Exception:
            pass

        # Mode 2: grep content search
        all_results = {}
        for sd in search_dirs:
            try:
                cmd = ["grep", "-rn", "--max-count=5"]
                if file_glob:
                    cmd.append(f"--include={file_glob}")
                cmd.extend([pattern, sd])
                result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=30)
                if result.stdout.strip():
                    for line in result.stdout.strip().split("\n")[:10]:
                        all_results[line] = True
            except Exception:
                pass

        if all_results:
            lines = list(all_results.keys())[:30]
            return "\n".join(lines)

    return json.dumps({"error": "Eşleşme bulunamadı", "searched": search_dirs}, ensure_ascii=False)


# ─── WEB ARAMA ────────────────────────────────────────────

@register_tool(
    name="web_search",
    description="Web'de ara. DuckDuckGo kullanir.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Arama sorgusu"},
            "max_results": {"type": "integer", "description": "Max sonuç", "default": 5},
            "safe_search": {"type": "boolean", "description": "Güvenli arama filtresi aktif", "default": True},
            "language": {"type": "string", "description": "Dil filtresi (örn: tr, en, de). Boş bırakılırsa tüm diller.", "default": ""},
        },
        "required": ["query"],
    },
    toolset="web",
)
async def web_search_tool(query: str, max_results: int = 5, safe_search: bool = True, language: str = "") -> str:
    """Web araması yap. DuckDuckGo kullanır. Hata alırsa alternatif dener."""
    from knowledge.web_search import web_search
    
    extra_kwargs = {"max_results": max_results}
    if not safe_search:
        extra_kwargs["safesearch"] = "off"
    else:
        extra_kwargs["safesearch"] = "on"
    if language:
        region_map = {
            "tr": "tr-tr", "en": "us-en", "de": "de-de",
            "fr": "fr-fr", "es": "es-es", "it": "it-it",
            "pt": "pt-pt", "nl": "nl-nl", "ru": "ru-ru",
            "ja": "jp-jp", "zh": "cn-zh", "ar": "wt-wt",
        }
        extra_kwargs["region"] = region_map.get(language.lower(), "wt-wt")
    
    try:
        # Ana sorgu - DuckDuckGo
        results = web_search.search_web(query, **extra_kwargs)
        
        if len(results) < 2:
            alt_query = query.replace("kimdir", "").replace("kim", "").replace("nedir", "").strip()
            if alt_query and alt_query != query:
                alt_results = web_search.search_web(alt_query, **extra_kwargs)
                results.extend(alt_results)
        
        return json.dumps(results[:max_results], ensure_ascii=False)
        
    except Exception as e:
        _err_msg = str(e)
        _error_info = ""
        if "timeout" in _err_msg.lower() or "connection" in _err_msg.lower() or "blocked" in _err_msg.lower():
            _error_info = " (muhtemelen Google/DDG engelledi)"
        
        # Alternatif: web_fetch ile dogrudan ara
        try:
            from tools.builtin.basic import web_fetch_tool
            _alt_query = query.replace(" ", "+")
            _url = f"https://html.duckduckgo.com/html/?q={_alt_query}"
            _alt_result = await web_fetch_tool(_url)
            return json.dumps({
                "success": True,
                "query": query,
                "alternative": True,
                "note": f"DuckDuckGo dogrudan sorgu engellendi{_error_info}, web_fetch ile HTML sayfasi cekildi",
                "results": [{"title": "DuckDuckGo HTML sonucu", "body": str(_alt_result)[:2000], "source": _url}]
            }, ensure_ascii=False)
        except Exception:
            return json.dumps({"error": f"Arama basarisiz{_error_info}: {_err_msg[:200]}"})


# ─── WEB FETCH ──────────────────────────────────────────

@register_tool(
    name="web_fetch",
    description="URL'den icerik cek. method, headers, css_selector ile ozellestir.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL"},
            "max_size": {"type": "integer", "description": "Maksimum karakter sayısı (varsayılan 5000, max 100000)", "default": 5000},
            "extract_text": {"type": "boolean", "description": "HTML'den metin çıkarma (varsayılan True)", "default": True},
            "css_selector": {"type": "string", "description": "Sadece belirtilen CSS seçicisine uyan içeriği çıkar", "default": ""},
            "headers": {"type": "string", "description": "Özel HTTP başlıkları (JSON string)", "default": ""},
            "timeout": {"type": "integer", "description": "Zaman aşımı (saniye)", "default": 15},
            "raw": {"type": "boolean", "description": "İçeriği parse etmeden ham olarak döndür", "default": False},
            "method": {"type": "string", "description": "HTTP metodu (GET, POST vb.)", "default": "GET"},
            "data": {"type": "string", "description": "POST isteği için veri/gövde", "default": ""},
        },
        "required": ["url"],
    },
    toolset="web",
)
async def web_fetch_tool(
    url: str,
    max_size: int = 5000,
    extract_text: bool = True,
    css_selector: str = "",
    headers: str = "",
    timeout: int = 60,
    raw: bool = False,
    method: str = "GET",
    data: str = ""
) -> str:
    """URLden içerik çek (async). Gelişmiş seçeneklerle."""
    import httpx
    import json
    import time
    
    max_size = min(max_size, 100000)
    req_headers = {"User-Agent": "Mozilla/5.0 (compatible; DorinaAgent/2.0)"}
    
    if headers:
        parsed_headers = {}
        if isinstance(headers, dict):
            parsed_headers = headers
        else:
            parsed_headers = safe_json_loads(headers, {})
        if isinstance(parsed_headers, dict):
            pass
            
    method = method.upper()
    start_time = time.time()
    
    # Retry logic (1 retry on transient errors)
    retries = 1
    resp = None
    err_msg = ""
    for attempt in range(retries + 1):
        try:
            kwargs = {
                "timeout": timeout,
                "headers": req_headers,
                "follow_redirects": True
            }
            if method in ("POST", "PUT", "PATCH") and data:
                kwargs["content"] = data
                
            resp = httpx.request(method, url, **kwargs)
            resp.raise_for_status()
            break
        except httpx.HTTPStatusError as e:
            err_msg = f"HTTP hatası: {e.response.status_code} - {e.response.reason_phrase}"
            break
        except Exception as e:
            err_msg = str(e)
            # Network unreachable gibi kalici hatalarda retry yapma
            if "Network is unreachable" in err_msg or "getaddrinfo" in err_msg or "Name or service" in err_msg:
                return json.dumps({"error": f"🌐 Ağ hatası — siteye erişilemiyor: {err_msg[:150]}", "truncated": False})
            if attempt == retries:
                break
            await asyncio.sleep(1)

    if not resp:
        return json.dumps({"error": err_msg, "truncated": False})
        
    elapsed_ms = int((time.time() - start_time) * 1000)
    content_type = resp.headers.get("content-type", "")
    
    metadata = {
        "status_code": resp.status_code,
        "content_type": content_type,
        "content_length": len(resp.content),
        "url": str(resp.url),
        "elapsed_ms": elapsed_ms,
        "headers": dict(resp.headers)
    }

    raw_text = resp.text
    result_content = raw_text
    
    if not raw:
        if "application/json" in content_type:
            try:
                parsed = resp.json()
                result_content = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                result_content = raw_text
        elif "text/html" in content_type and extract_text:
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw_text, "html.parser")
                
                if css_selector:
                    elements = soup.select(css_selector)
                    soup = BeautifulSoup("".join(str(e) for e in elements), "html.parser")
                    
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                    
                result_content = soup.get_text(separator="\n", strip=True)
            except Exception:
                result_content = raw_text
                
    # Truncate and add preview
    truncated = False
    if len(result_content) > max_size:
        result_content = result_content[:max_size]
        truncated = True
        result_content += f"\n\n[... İÇERİK KESİLDİ. TOPLAM UZUNLUK: {len(raw_text)}, GÖSTERİLEN: {max_size} ...]"
        
    return json.dumps({
        "content": result_content,
        "metadata": metadata,
        "truncated": truncated
    }, ensure_ascii=False)


# ─── FILE PATCH (find-replace) ──────────────────────────

@register_tool(
    name="patch",
    description="Dosyada bul-değiştir. Tekli veya batch. start_line/end_line ile hedefli arama.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Dosya yolu"},
            "old_string": {"type": "string", "description": "Bulunacak metin (tekli değişiklik için)"},
            "new_string": {"type": "string", "description": "Yeni metin (tekli değişiklik için)"},
            "start_line": {"type": "integer", "description": "Sadece bu satırdan itibaren ara (opsiyonel)"},
            "end_line": {"type": "integer", "description": "Sadece bu satıra kadar ara (opsiyonel)"},
            "changes": {
                "type": "array",
                "description": "Aynı anda birden fazla değişiklik yapmak için list: [{'old_string': 'eski', 'new_string': 'yeni'}, ...]",
                "items": {
                    "type": "object",
                    "properties": {
                        "old_string": {"type": "string"},
                        "new_string": {"type": "string"}
                    },
                    "required": ["old_string", "new_string"]
                }
            },
            "dry_run": {"type": "boolean", "description": "Değişiklik yapmadan sadece göster (önizleme)", "default": False},
        },
        "required": ["path"],
    },
    toolset="file",
)
def patch_tool(path: str, old_string: str = "", new_string: str = "", changes: list = None, start_line: int = None, end_line: int = None, dry_run: bool = False) -> str:
    """Dosyada find-and-replace yap. Tekli veya çoklu destekler, Dry-run desteği."""
    p = Path(path).expanduser()
    if not p.exists():
        return json.dumps({"error": f"Dosya bulunamadı: {path}"})
    
    try:
        content = p.read_text(encoding="utf-8", errors="ignore")
        
        ops = []
        if changes:
            ops.extend(changes)
        if old_string:
            ops.append({"old_string": old_string, "new_string": new_string})
            
        if not ops:
            return json.dumps({"error": "Hiçbir değişiklik belirtilmedi (old_string veya changes gerekli)."})
        
        total_count = 0
        new_content = content
        preview_lines = []
        
        for op in ops:
            old_str = op.get("old_string", "")
            new_str = op.get("new_string", "")
            if not old_str: continue
            
            # Constrain to line range if provided
            lines = new_content.split('\n')
            _start_idx = max(0, start_line - 1) if start_line else 0
            _end_idx = min(len(lines), end_line) if end_line else len(lines)
            
            target_block = '\n'.join(lines[_start_idx:_end_idx])
            
            count = target_block.count(old_str)
            if count == 0:
                return json.dumps({"error": f"Aranan metin belirtilen aralikta bulunamadı: {old_str[:50]}"})
            
            total_count += count
            
            if dry_run:
                block_lines = target_block.split('\n')
                for i, line in enumerate(block_lines):
                    if old_str in line:
                        preview_lines.append({
                            "line": _start_idx + i + 1,
                            "content": line,
                            "replacement": line.replace(old_str, new_str),
                        })
            
            new_block = target_block.replace(old_str, new_str)
            
            # Reconstruct the file content
            new_content = '\n'.join(lines[:_start_idx] + [new_block] + lines[_end_idx:]) if lines else new_block
        
        if dry_run:
            return json.dumps({
                "success": True,
                "path": str(p),
                "dry_run": True,
                "count": total_count,
                "preview": preview_lines[:20],
                "message": f"{total_count} değişiklik bulundu (dry-run — dosyaya yazılmadı)",
            }, ensure_ascii=False)
        
        p.write_text(new_content, encoding="utf-8")
        
        # Verification: find changed lines and show ±2 context
        _old_lines = content.split("\n")
        _new_lines = new_content.split("\n")
        _verification = []
        for _i, (_ol, _nl) in enumerate(zip(_old_lines, _new_lines)):
            if _ol != _nl:
                _start = max(0, _i - 2)
                _end = min(len(_new_lines), _i + 3)
                _ctx = []
                for _j in range(_start, _end):
                    _mark = ">" if _j == _i else " "
                    _ctx.append(f"{_mark} {_j+1}|{_new_lines[_j]}")
                _verification.append({
                    "line": _i + 1,
                    "context": _ctx,
                })
        # If line counts differ (insertion/deletion), capture remaining
        if len(_new_lines) != len(_old_lines):
            for _i in range(min(len(_old_lines), len(_new_lines)), max(len(_old_lines), len(_new_lines))):
                if _i < len(_new_lines):
                    _start = max(0, _i - 2)
                    _end = min(len(_new_lines), _i + 3)
                    _ctx = []
                    for _j in range(_start, _end):
                        _mark = ">" if _j == _i else " "
                        _ctx.append(f"{_mark} {_j+1}|{_new_lines[_j]}")
                    _verification.append({
                        "line": _i + 1,
                        "context": _ctx,
                    })
        
        return json.dumps({
            "success": True,
            "path": str(p),
            "count": total_count,
            "changes": total_count,
            "bytes": len(new_content),
            "verification": {
                "changed_lines": _verification[:10],  # max 10 changed regions
                "summary": f"{len(_verification)} satir degisti. Degisiklik dogru mu diye TEKRAR read_file yapma. Verification yukarida."
            },
        })
    except Exception as e:
        return json.dumps({"error": str(e)})



@register_tool(
    name="batch_python",
    description="Python script'ini calistir ve ciktiyi getir. 20+ dosya taramasi, toplu veri analizi, regex taramalari icin IDEAL. Tek seferde calisir, cok daha hizli.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Calistirilacak Python kodu. print() ile cikti al."},
            "timeout": {"type": "integer", "description": "Zaman asimi (saniye)", "default": 30},
            "sandbox": {"type": "boolean", "description": "Docker container'da calistir. Varsayilan: config.yaml tools.sandbox ayarina gore", "default": None},
        },
        "required": ["code"],
    },
    toolset="development",
)
async def batch_python_tool(code: str, timeout: int = 30, sandbox: bool = None) -> str:
    """Python script'ini calistir. Toplu taramalar icin (import, dosya, regex)."""
    # ── Sandbox routing ────────────────────────────────────
    if sandbox is None:
        sandbox = _sandbox_enabled_in_config()
    if sandbox:
        sandbox_result = _run_python_in_sandbox(code, timeout=timeout)
        if sandbox_result is not None:
            return sandbox_result
        # Sandbox unavailable — fall through to host execution

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
                return json.dumps({"error": f"Cikis kodu {r.returncode}", "stderr": err, "stdout": out})
            return out or "Basarili (cikti yok)"
        except subprocess.TimeoutExpired:
            return json.dumps({"error": f"Zaman asimi ({timeout}sn)"})
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            os.unlink(f.name)


# ─── TOOLSET YONETIMI ────────────────────────────────────

@register_tool(
    name="tools_enable",
    description="Yeni bir tool kategorisini aktiflestir. Ornek: tools_enable('GIT'), tools_enable('CRON'). Default acik: FILE, WEB, TERMINAL.",
    parameters={
        "type": "object",
        "properties": {
            "toolset": {
                "type": "string",
                "description": "Kategori: file, web, terminal, git, memory, cron, delegation, sandbox, graphify, research, vision, mcp, system",
                "enum": ["file", "web", "terminal", "git", "memory", "cron", "delegation", "sandbox", "graphify", "research", "vision", "mcp", "system"],
            }
        },
        "required": ["toolset"],
    },
    toolset="system",
)
def tools_enable_tool(toolset: str) -> str:
    from tools.toolset import tools_enable
    return tools_enable(toolset)
