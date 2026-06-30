"""
Yeni modüllerden tool'lar — providers, search, browser, agents, mail, sandbox.
"""

from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool, registry
from core.logger import log


# ─── PROVIDER TOOL'LARI ─────────────────────────

@register_tool(
    name="list_providers",
    description="Kullanılabilir LLM sağlayıcılarını listele.",
    parameters={"type": "object", "properties": {}},
    toolset="system",
)
def list_providers_tool() -> str:
    """Kullanılabilir LLM sağlayıcılarını listele."""
    from providers.router import router
    # Add default providers
    if not router.providers:
        router.add_provider("deepseek", "deepseek/deepseek-v4-flash", weight=1)
        router.add_provider("groq", "groq/llama3-70b-8192", weight=2)
        router.add_provider("ollama", "ollama/llama3", weight=3)
    return json.dumps(router.list(), ensure_ascii=False)


@register_tool(
    name="switch_provider",
    description="LLM sağlayıcısını değiştir. DeepSeek, Groq, Ollama.",
    parameters={
        "type": "object",
        "properties": {
            "provider": {"type": "string", "description": "Sağlayıcı adı"},
        },
        "required": ["provider"],
    },
    toolset="system",
)
def switch_provider_tool(provider: str) -> str:
    from providers.router import router
    for i, p in enumerate(router.providers):
        if p["name"].lower() == provider.lower():
            router._current = i
            return json.dumps({"success": True, "provider": provider})
    return json.dumps({"error": f"Sağlayıcı bulunamadı: {provider}"})


# ─── SEARCH TOOL'LARI ───────────────────────────


# ─── BROWSER TOOL'LARI ──────────────────────────

@register_tool(
    name="browser_navigate",
    description="Web tarayıcıda bir sayfaya git, isteğe bağlı ekran görüntüsü al veya sayfa metnini çıkar.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Gidilecek URL"},
            "screenshot": {"type": "boolean", "description": "Sayfanın ekran görüntüsünü al", "default": False},
            "screenshot_path": {"type": "string", "description": "Ekran görüntüsü kayıt yolu (opsiyonel, varsayılan: /tmp/dorina_screenshot.png)", "default": ""},
            "extract_text": {"type": "boolean", "description": "Sayfanın tüm metnini çıkar", "default": False},
        },
        "required": ["url"],
    },
    toolset="browser",
)
async def browser_navigate_tool(url: str, screenshot: bool = False,
                                 screenshot_path: str = "",
                                 extract_text: bool = False) -> str:
    """Async browser navigate: sayfaya git, opsiyonel screenshot/metin çıkar."""
    from browser.client import browser
    result_parts = []

    # Sayfaya git
    nav_result = await browser.navigate(url)
    result_parts.append(nav_result)
    if "yuklenemedi" in nav_result.lower():
        await browser.close()
        return nav_result

    # Screenshot
    if screenshot:
        if screenshot_path:
            ss_result = await browser.screenshot(path=screenshot_path)
        else:
            ss_result = await browser.screenshot()
        result_parts.append(ss_result)

    # Extract page text
    if extract_text:
        page_text = await browser.get_text()
        result_parts.append(f"--- Sayfa metni ({len(page_text)} karakter) ---")
        result_parts.append(page_text)

    await browser.close()
    return "\n".join(result_parts)


# ─── SANDBOX TOOL'U ─────────────────────────────

@register_tool(
    name="sandbox_exec",
    description="Python kodunu veya shell komutunu güvenli Docker sandbox'ta çalıştır — izole, güvenli, ağ yok, disk read-only. type='python' için Python sandbox, type='shell' için bash sandbox.",
    parameters={
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["python", "shell"],
                "default": "shell",
                "description": "Çalıştırma türü: 'python' veya 'shell'",
            },
            "code": {
                "type": "string",
                "description": "(python) Çalıştırılacak Python kodu",
            },
            "command": {
                "type": "string",
                "description": "(shell) Çalıştırılacak shell komutu",
            },
            "timeout": {
                "type": "integer",
                "description": "Zaman aşımı (saniye)",
                "default": 30,
            },
        },
        "required": [],
    },
    toolset="development",
)
async def sandbox_exec_tool(type_: str = "shell", code: str = "", command: str = "", timeout: int = 30) -> str:
    """Merged sandbox tool — dispatches by type parameter."""
    if type_ == "python":
        from sandbox.docker import sandbox
        return sandbox.run_python(code)
    else:  # "shell"
        from tools.security import sandbox_terminal
        return await sandbox_terminal(command, timeout)


# ─── VISION TOOL'U ──────────────────────────────

@register_tool(
    name="analyze_image",
    description="Resim dosyasını analiz et: format, boyut, renk modu, dosya boyutu.",
    parameters={
        "type": "object",
        "properties": {
            "image_path": {"type": "string", "description": "Resim dosya yolu (jpg, png, gif, bmp, webp)"},
        },
        "required": ["image_path"],
    },
    toolset="vision",
)
def analyze_image_tool(image_path: str) -> str:
    """Resmi analiz et: format, boyut, renk, dosya bilgisi."""
    from vision.analyzer import vision
    try:
        from PIL import Image
        p = Path(image_path).expanduser()
        if not p.exists():
            return json.dumps({"error": f"Dosya bulunamadı: {image_path}"})
        img = Image.open(p)
        info = {
            "file": str(p),
            "size_bytes": p.stat().st_size,
            "format": img.format or "bilinmiyor",
            "dimensions": f"{img.size[0]}x{img.size[1]}",
            "mode": img.mode,
            "megapixels": round(img.size[0] * img.size[1] / 1_000_000, 2),
        }
        # EXIF varsa
        exif = img.getexif()
        if exif:
            from PIL.ExifTags import TAGS
            for k, v in exif.items():
                tag = TAGS.get(k, k)
                if tag in ("Make", "Model", "DateTimeOriginal", "Software"):
                    info[tag] = str(v)
        return json.dumps(info, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Analiz edilemedi: {e}"})



