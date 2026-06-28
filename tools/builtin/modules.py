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

@register_tool(
    name="web_search_multi",
    description="Birden çok kaynaktan web araması yap.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Arama sorgusu"},
            "max_results": {"type": "integer", "description": "Maksimum sonuç", "default": 5},
        },
        "required": ["query"],
    },
    toolset="web",
)
def web_search_multi_tool(query: str, max_results: int = 5) -> str:
    from search.engine import SearchEngine
    se = SearchEngine()
    results = se.search(query, max_results)
    return json.dumps(results, ensure_ascii=False)


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


# ─── AGENTS TOOL'LARI ───────────────────────────

@register_tool(
    name="run_crew",
    description="Multi-agent ekibi çalıştır. Planner + Researcher + Writer.",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "Yapılacak görev"},
        },
        "required": ["task"],
    },
    toolset="delegation",
)
def run_crew_tool(task: str) -> str:
    from agents.crew import AgentCrew
    crew = AgentCrew()
    crew.add_member("planner", "Görevi planla")
    crew.add_member("researcher", "Araştırma yap")
    crew.add_member("writer", "Rapor yaz")
    result = crew.run(task)
    return result


# ─── SANDBOX TOOL'U ─────────────────────────────

@register_tool(
    name="sandbox_python",
    description="Python kodunu güvenli sandbox'ta çalıştır.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Çalıştırılacak Python kodu"},
        },
        "required": ["code"],
    },
    toolset="development",
)
def sandbox_python_tool(code: str) -> str:
    from sandbox.docker import sandbox
    return sandbox.run_python(code)


@register_tool(
    name="sandbox_terminal",
    description="Shell komutunu Docker sandbox'ta çalıştır — izole, güvenli, ağ yok, disk read-only.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Çalıştırılacak komut"},
            "timeout": {"type": "integer", "description": "Zaman aşımı (saniye)", "default": 60},
        },
        "required": ["command"],
    },
    toolset="development",
)
def sandbox_terminal_tool(command: str, timeout: int = 60) -> str:
    from tools.security import sandbox_terminal
    return sandbox_terminal(command, timeout)


# ─── MAIL TOOL'U ────────────────────────────────

@register_tool(
    name="send_email",
    description="E-posta gönder.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Alıcı e-posta adresi"},
            "subject": {"type": "string", "description": "Konu"},
            "body": {"type": "string", "description": "Mesaj içeriği"},
        },
        "required": ["to", "subject", "body"],
    },
    toolset="communication",
)
def send_email_tool(to: str, subject: str, body: str) -> str:
    from mail.client import email
    ok = email.send(to, subject, body)
    return json.dumps({"success": ok})


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


# ─── WORKFLOW TOOL'U ────────────────────────────

@register_tool(
    name="run_workflow",
    description="Çok adımlı iş akışı çalıştır.",
    parameters={
        "type": "object",
        "properties": {
            "steps": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Adım listesi: [{\"name\": \"...\", \"action\": \"...\"}]",
            },
        },
        "required": ["steps"],
    },
    toolset="development",
)
def run_workflow_tool(steps: list[dict]) -> str:
    from workflows.runner import workflows
    workflows.define(steps)
    return workflows.run()
