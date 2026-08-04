"""Dependency healing module. Auto-installs missing packages on ImportError."""

import re
import subprocess
from core.logger import log

def missing_module(exception: Exception) -> str | None:
    """Extract missing module name from ImportError/ModuleNotFoundError."""
    if not isinstance(exception, ImportError):
        return None
        
    # Python 3.6+ has name attribute on ImportError
    if getattr(exception, "name", None):
        return exception.name
        
    msg = str(exception)
    match = re.search(r"No module named '([^']+)'", msg)
    if match:
        return match.group(1)
        
    return None

def pip_name(mod: str) -> str:
    """Map module name to pip package name."""
    mod = mod.lower()
    mapping = {
        "yaml": "PyYAML",
        "cv2": "opencv-python",
        "pil": "Pillow",
        "bs4": "beautifulsoup4",
        "dotenv": "python-dotenv",
        "jwt": "PyJWT",
        "dateutil": "python-dateutil",
        "github": "PyGithub",
        "git": "GitPython"
    }
    return mapping.get(mod, mod)

def install(pkg: str) -> bool:
    """Attempt to install package using uv or pip."""
    log.info(f"⌛ '{pkg}' kuruluyor... (Auto-healing dependency)")
    
    # Try uv first
    try:
        result = subprocess.run(
            ["uv", "pip", "install", pkg],
            capture_output=True,
            timeout=60,
            text=True
        )
        if result.returncode == 0:
            log.info(f"✅ '{pkg}' uv ile kuruldu.")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
        
    # Fallback to pip
    try:
        result = subprocess.run(
            ["pip", "install", pkg],
            capture_output=True,
            timeout=60,
            text=True
        )
        if result.returncode == 0:
            log.info(f"✅ '{pkg}' pip ile kuruldu.")
            return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
        
    log.error(f"❌ '{pkg}' kurulamadı.")
    return False
