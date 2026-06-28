"""
E-posta tool'ları — email_read, email_send, email_list, email_search.
Hermes/Odysseus pattern: @register_tool ile kayıt.
"""

from __future__ import annotations
import json

from tools.registry import register_tool
from core.logger import log


# ═══════════════════════════════════════════════════════════════
# email_send — E-posta gönderme
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="email_send",
    description="E-posta gönder. Alıcı, konu ve içerik belirt.",
    parameters={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Alıcı e-posta adresi"},
            "subject": {"type": "string", "description": "E-posta konusu"},
            "body": {"type": "string", "description": "E-posta içeriği (düz metin)"},
        },
        "required": ["to", "subject", "body"],
    },
    toolset="communication",
)
async def email_send(to: str, subject: str, body: str) -> str:
    """E-posta gönder (IMAP/SMTP)."""
    from mail.client import email_client
    ok = await email_client.send_async(to, subject, body)
    if ok:
        return json.dumps({"success": True, "message": f"E-posta gonderildi: {to} -> {subject}"}, ensure_ascii=False)
    return json.dumps({"success": False, "error": "E-posta gonderilemedi. Ayarlari kontrol edin (config.yaml / .env)."}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# email_list — Gelen kutusu listesi
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="email_list",
    description="Gelen kutusundaki e-postaları listele.",
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maksimum e-posta sayısı (varsayılan: 10)",
                "default": 10,
            },
            "folder": {
                "type": "string",
                "description": "Klasör adı (varsayılan: INBOX)",
                "default": "INBOX",
            },
        },
        "required": [],
    },
    toolset="communication",
)
async def email_list(limit: int = 10, folder: str = "INBOX") -> str:
    """Gelen kutusundaki e-postaları listele."""
    from mail.client import email_client
    mails = await email_client.read_inbox_async(limit=limit, folder=folder)
    if not mails:
        return json.dumps({"emails": [], "message": "E-posta bulunamadi veya IMAP ayarlari eksik"}, ensure_ascii=False)
    return json.dumps({"emails": mails, "count": len(mails)}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# email_read — Belirli e-postayı oku
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="email_read",
    description="Belirli bir e-postanın tam içeriğini oku.",
    parameters={
        "type": "object",
        "properties": {
            "email_id": {
                "type": "string",
                "description": "E-posta ID'si (email_list'ten alınır)",
            },
            "folder": {
                "type": "string",
                "description": "Klasör adı (varsayılan: INBOX)",
                "default": "INBOX",
            },
        },
        "required": ["email_id"],
    },
    toolset="communication",
)
async def email_read(email_id: str, folder: str = "INBOX") -> str:
    """Belirli bir e-postanın tam detayını oku."""
    from mail.client import email_client
    detail = email_client.read_email_detail(email_id, folder=folder)
    if detail:
        return json.dumps(detail, ensure_ascii=False)
    return json.dumps({"error": f"E-posta bulunamadi: {email_id}"}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# email_search — E-postalarda ara
# ═══════════════════════════════════════════════════════════════

@register_tool(
    name="email_search",
    description="E-postalarda ara. Gönderen, konu veya içerikte arama yapar.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Arama sorgusu (gönderen, konu veya içerikte aranır)",
            },
            "folder": {
                "type": "string",
                "description": "Klasör adı (varsayılan: INBOX)",
                "default": "INBOX",
            },
            "limit": {
                "type": "integer",
                "description": "Maksimum sonuç sayısı (varsayılan: 20)",
                "default": 20,
            },
        },
        "required": ["query"],
    },
    toolset="communication",
)
async def email_search(query: str, folder: str = "INBOX", limit: int = 20) -> str:
    """E-postalarda ara (IMAP SEARCH)."""
    from mail.client import email_client
    results = email_client.search_emails(query, folder=folder, limit=limit)
    if results:
        return json.dumps({"results": results, "count": len(results)}, ensure_ascii=False)
    return json.dumps({"results": [], "message": "E-posta bulunamadi"}, ensure_ascii=False)
