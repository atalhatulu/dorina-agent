"""
Gelişmiş tool'lar — Deep Research, MCP, Delegate, Email, Audio.
"""

from __future__ import annotations
import json

from tools.registry import register_tool, registry
from core.logger import log


# ─── DELEGATE TASK (Alt-Agent) ───────────────────────────

@register_tool(
    name="delegate_task",
    description="Bir alt-agent'a görev ver. Paralel çalışır, sonucu özet olarak döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "goal": {
                "type": "string",
                "description": "Alt-agent'ın yapacağı görev",
            },
            "context": {
                "type": "string",
                "description": "Alt-agent'a verilecek bağlam/bilgi",
                "default": "",
            },
        },
        "required": ["goal"],
    },
    toolset="delegation",
)
def delegate_task_tool(goal: str, context: str = "") -> str:
    """Alt-agent'a görev ver, sonucu bekle."""
    from tools.delegate import delegate
    
    agent_id = delegate.submit(goal=goal, context=context)
    result = delegate.get_result(agent_id, timeout=120)
    
    agent = delegate.active.get(agent_id)
    return json.dumps({
        "agent_id": agent_id,
        "result": result,
        "status": agent.status if agent else "unknown",
        "turns": agent.turn_count if agent else 0,
    }, ensure_ascii=False)


# ─── DELEGATE BATCH (Paralel Alt-Agent) ─────────────────

@register_tool(
    name="delegate_batch",
    description="Birden çok alt-agent'ı paralel çalıştır. Her birine farklı görev ver.",
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "goal": {"type": "string"},
                        "context": {"type": "string", "default": ""},
                    },
                },
                "description": "Görev listesi: [{\"goal\": \"...\", \"context\": \"...\"}, ...]",
            },
        },
        "required": ["tasks"],
    },
    toolset="delegation",
)
def delegate_batch_tool(tasks: list[dict]) -> str:
    """Paralel alt-agent çalıştır."""
    from tools.delegate import delegate
    
    ids = delegate.submit_batch(tasks)
    results = []
    for aid in ids:
        result = delegate.get_result(aid, timeout=120)
        agent = delegate.active.get(aid)
        results.append({
            "agent_id": aid,
            "result": result,
            "status": agent.status if agent else "unknown",
        })
    
    return json.dumps({"results": results}, ensure_ascii=False)


# ─── DEEP RESEARCH ─────────────────────────────────────────

@register_tool(
    name="deep_research",
    description="Derinlemesine web araştırması yap. Çok adımlı arama + sentez.",
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Araştırılacak soru/konu",
            },
        },
        "required": ["question"],
    },
    toolset="research",
)
async def deep_research_tool(question: str) -> str:
    """Iteratif deep research başlat (async)."""
    from knowledge.deep_research import DeepResearcher

    researcher = DeepResearcher()
    report = await researcher.research(question)
    stats = researcher.get_stats()

    result = {
        "report": report,
        "stats": stats,
    }
    return json.dumps(result, ensure_ascii=False)


# ─── MCP TOOL LIST ──────────────────────────────────────

@register_tool(
    name="mcp_list_tools",
    description="MCP sunucularındaki tüm tool'ları listele.",
    parameters={
        "type": "object",
        "properties": {},
    },
    toolset="mcp",
    check_fn=lambda: False,  # Varsayılan kapalı, MCP varsa açılır
)
async def mcp_list_tools_tool() -> str:
    """MCP tool'larını listele."""
    from tools.mcp.client import mcp_manager
    tools = await mcp_manager.list_all_tools()
    if not tools:
        return json.dumps({"error": "MCP sunucusu bağlı değil"})
    
    result = [
        {"name": t.name, "description": t.description[:100], "server": t.server_name}
        for t in tools
    ]
    return json.dumps(result, ensure_ascii=False)


# ─── MCP TOOL CALL ──────────────────────────────────────

@register_tool(
    name="mcp_call_tool",
    description="MCP sunucusundaki bir tool'u çağır.",
    parameters={
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "description": "Çağrılacak MCP tool adı",
            },
            "arguments": {
                "type": "object",
                "description": "Tool parametreleri",
                "default": {},
            },
        },
        "required": ["tool_name"],
    },
    toolset="mcp",
    check_fn=lambda: False,
)
async def mcp_call_tool_tool(tool_name: str, arguments: dict = None) -> str:
    """MCP tool'unu çağır."""
    from tools.mcp.client import mcp_manager
    args = arguments or {}
    return await mcp_manager.call_tool(tool_name, args)


# ═══════════════════════════════════════════════════════════════
# AUDIO / VOICE TOOL'LARI
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="tts_speak",
    description="Metni sese çevir (Text-to-Speech). edge-tts ile MP3 dosyası oluşturur.",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Konuşulacak metin"},
            "lang": {"type": "string", "description": "Dil kodu (tr, en, de, fr, ...)", "default": "tr"},
            "voice": {"type": "string", "description": "Ses adı (opsiyonel, örn. tr-TR-EmelNeural)", "default": ""},
        },
        "required": ["text"],
    },
    toolset="audio",
)
async def tts_speak(text: str, lang: str = "tr", voice: str = "") -> str:
    """Metni sese çevir."""
    from audio.tts import tts_engine
    voice_arg = voice if voice else None
    path = await tts_engine.speak(text, lang=lang, voice=voice_arg)
    return path


@register_tool(
    name="stt_transcribe",
    description="Ses dosyasını metne çevir (Speech-to-Text). Whisper ile transkripsiyon.",
    parameters={
        "type": "object",
        "properties": {
            "audio_path": {"type": "string", "description": "Ses dosyası yolu (.wav, .mp3, .m4a, .ogg)"},
            "language": {"type": "string", "description": "Dil kodu (opsiyonel, örn. tr, en)", "default": ""},
        },
        "required": ["audio_path"],
    },
    toolset="audio",
)
async def stt_transcribe(audio_path: str, language: str = "") -> str:
    """Ses dosyasını metne çevir."""
    from audio.stt import stt_engine
    lang = language if language else None
    text = await stt_engine.transcribe(audio_path, language=lang)
    return text


@register_tool(
    name="mic_record",
    description="Mikrofondan ses kaydet. Belirtilen süre kadar kayıt yapar ve WAV dosyası döndürür.",
    parameters={
        "type": "object",
        "properties": {
            "duration": {"type": "integer", "description": "Kayıt süresi (saniye)", "default": 5},
        },
        "required": [],
    },
    toolset="audio",
)
async def mic_record(duration: int = 5) -> str:
    """Mikrofondan ses kaydet."""
    from audio.microphone import mic
    path = await mic.record(duration=duration)
    return path


@register_tool(
    name="mic_list_devices",
    description="Kullanılabilir mikrofon cihazlarını listele.",
    parameters={
        "type": "object",
        "properties": {},
    },
    toolset="audio",
)
async def mic_list_devices() -> str:
    """Mikrofon cihazlarını listele."""
    from audio.microphone import mic
    return mic.list_devices()

