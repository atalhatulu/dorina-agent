"""API error classification — Hermes-inspired error taxonomy.

Categorizes LLM API errors into structured recovery actions:
retry, rotate credential, fallback, compress context, or abort.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any


class FailoverReason:
    """API error categories — determines recovery strategy."""
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    OVERLOADED = "overloaded"
    SERVER_ERROR = "server_error"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"
    PAYLOAD_TOO_LARGE = "payload_too_large"
    MODEL_NOT_FOUND = "model_not_found"
    CONTENT_POLICY_BLOCKED = "content_policy_blocked"
    FORMAT_ERROR = "format_error"
    TOOL_FORMAT_ERROR = "tool_format_error"
    NETWORK = "network"
    TOOL_ERROR = "tool_error"
    PARSE_ERROR = "parse_error"
    UNKNOWN = "unknown"


@dataclass
class ClassifiedError:
    """Structured classification with recovery hints."""
    reason: str
    status_code: Optional[int] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    message: str = ""
    error_context: dict[str, Any] = field(default_factory=dict)
    retryable: bool = True
    should_compress: bool = False
    should_rotate_credential: bool = False
    should_fallback: bool = False

    @property
    def is_auth(self) -> bool:
        return self.reason in (FailoverReason.AUTH, FailoverReason.AUTH_PERMANENT)


# ── Error patterns ─────────────────────────────────────────

_BILLING_PATTERNS = [
    "insufficient_quota", "insufficient quota", "insufficient credits",
    "credit balance", "credits exhausted", "no usable credits",
    "payment required", "billing hard limit", "exceeded your current quota",
    "out of funds", "balance_depleted", "quota exceeded",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit", "rate_limit", "too many requests", "throttled",
    "requests per minute", "tokens per minute", "try again in",
    "please retry after", "resource_exhausted", "429",
]

_CONTEXT_OVERFLOW_PATTERNS = [
    "context length", "context_length", "max context", "token limit",
    "maximum context", "context window", "too many tokens",
    "reduce the length", "maximum prompt length",
]

_TOOL_FORMAT_PATTERNS = [
    "tool_calls", "tool calls", "tool_call_id", "tool_call",
    "must be a response to a preceding message",
    "invalid tool", "tool not found",
]

_CONTENT_POLICY_PATTERNS = [
    "content_policy", "safety", "harmful", "inappropriate",
    "content_filter", "blocked by", "policy violation",
]

_MODEL_NOT_FOUND_PATTERNS = [
    "model not found", "model_not_found", "invalid model",
    "does not exist", "not found",
]

_OVERLOADED_PATTERNS = [
    "overloaded", "503", "529", "service unavailable",
    "temporarily unavailable", "capacity",
]

_SERVER_ERROR_PATTERNS = [
    "500", "502", "internal server error", "server error",
    "bad gateway", "gateway timeout",
]


def _extract_status_code(error: Exception) -> Optional[int]:
    status = getattr(error, "status_code", None)
    if status is not None:
        return int(status)
    resp = getattr(error, "response", None)
    if resp is not None:
        return getattr(resp, "status_code", None)
    return None


def _extract_error_msg(error: Exception) -> str:
    parts = [str(error).lower()]
    for attr in ("body", "message", "response"):
        obj = getattr(error, attr, None)
        if isinstance(obj, str) and obj:
            if obj.lower() not in parts[0]:
                parts.append(obj.lower())
        elif isinstance(obj, dict):
            err_inner = obj.get("error", {})
            if isinstance(err_inner, dict):
                msg = err_inner.get("message", "")
            else:
                msg = str(err_inner)
            if not msg:
                msg = obj.get("message", "")
            if msg and msg.lower() not in parts[0]:
                parts.append(msg.lower())
    return " ".join(parts)


def classify_api_error(
    error: Exception,
    *,
    provider: str = "",
    model: str = "",
) -> ClassifiedError:
    """Classify an API error into structured recovery recommendation."""
    status = _extract_status_code(error)
    error_msg = _extract_error_msg(error)

    # DeepSeek tool format error — specific case
    if "tool" in error_msg and "must be a response" in error_msg:
        return ClassifiedError(
            reason=FailoverReason.TOOL_FORMAT_ERROR,
            status_code=status, provider=provider, model=model,
            message=str(error)[:200],
            retryable=False, should_fallback=True,
        )

    # Pattern matching in priority order
    checks = [
        (FailoverReason.CONTENT_POLICY_BLOCKED, _CONTENT_POLICY_PATTERNS, False, False, True),
        (FailoverReason.BILLING, _BILLING_PATTERNS, False, True, True),
        (FailoverReason.RATE_LIMIT, _RATE_LIMIT_PATTERNS, True, True, False),
        (FailoverReason.CONTEXT_OVERFLOW, _CONTEXT_OVERFLOW_PATTERNS, False, True, False),
        (FailoverReason.MODEL_NOT_FOUND, _MODEL_NOT_FOUND_PATTERNS, False, False, True),
        (FailoverReason.OVERLOADED, _OVERLOADED_PATTERNS, True, False, True),
        (FailoverReason.SERVER_ERROR, _SERVER_ERROR_PATTERNS, True, False, True),
    ]

    for reason, patterns, retryable, compress, fallback in checks:
        if any(p in error_msg for p in patterns):
            c = ClassifiedError(
                reason=reason, status_code=status,
                provider=provider, model=model,
                message=str(error)[:200],
                retryable=retryable, should_compress=compress,
                should_fallback=fallback,
            )
            if reason == FailoverReason.RATE_LIMIT:
                c.should_rotate_credential = True
            return c

    # Classify by HTTP status code
    if status:
        status_map = {
            401: (FailoverReason.AUTH, True, False, True),
            402: (FailoverReason.BILLING, False, False, True),
            403: (FailoverReason.AUTH, False, False, True),
            404: (FailoverReason.MODEL_NOT_FOUND, False, False, True),
            413: (FailoverReason.PAYLOAD_TOO_LARGE, False, True, False),
            429: (FailoverReason.RATE_LIMIT, True, False, True),
            500: (FailoverReason.SERVER_ERROR, True, False, True),
            502: (FailoverReason.SERVER_ERROR, True, False, True),
            503: (FailoverReason.OVERLOADED, True, False, False),
        }
        if status in status_map:
            reason, retryable, compress, fallback = status_map[status]
            return ClassifiedError(
                reason=reason, status_code=status,
                provider=provider, model=model,
                message=str(error)[:200],
                retryable=retryable, should_compress=compress,
                should_fallback=fallback,
            )

    return ClassifiedError(
        reason=FailoverReason.UNKNOWN, status_code=status,
        provider=provider, model=model,
        message=str(error)[:200],
        retryable=True, should_fallback=True,
    )


# ── Tool error sanitization ────────────────────────────────

TOOL_ERROR_PREFIX = "[TOOL_ERROR]"


def sanitize_tool_error(error_msg: str, max_len: int = 2000) -> str:
    """Sanitize tool error for LLM consumption (strip XML, code fences)."""
    import re
    cleaned = re.sub(r'<[^>]+>', '', error_msg)
    cleaned = re.sub(r'```.*?```', '', cleaned, flags=re.DOTALL)
    cleaned = cleaned.replace(TOOL_ERROR_PREFIX, "").strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len] + "..."
    return f"{TOOL_ERROR_PREFIX} {cleaned}"


# ── User-facing error formatting ──────────────────────────

ERROR_USER_MESSAGES: dict[str, dict[str, str]] = {
    FailoverReason.TOOL_FORMAT_ERROR: {
        "title": "🔧 Mesaj Sırası Hatası",
        "what": "LLM'in çağırdığı araç (tool) ile dönen sonuç arasındaki mesaj sırası bozuldu.",
        "why": "Bu genellikle Ctrl+C ile işlem yarıda kesildiğinde veya LLM'in araç çağrıları "
               "arasına beklenmeyen bir mesaj girdiğinde olur. DeepSeek gibi modeller sıkı "
               "bir assistant(tool_calls) → tool mesaj sırası bekler.",
        "action": "Sistem mesaj sırasını otomatik onardı ve yeniden deniyor. "
                  "Bu genellikle birkaç saniye içinde çözülür.\n"
                  "  → /retry ile manuel tekrar dene\n"
                  "  → /new ile yeni oturum başlat",
    },
    FailoverReason.NETWORK: {
        "title": "🌐 Network Hatası",
        "what": "API sunucusuna bağlanılamadı veya bağlantı koptu.",
        "why": "İnternet bağlantınız zayıf olabilir, API servisi geçici olarak kapalı olabilir, "
               "veya bir DNS/proxy sorunu olabilir.",
        "action": "Birkaç saniye bekleyip tekrar deneyin. Eğer sorun devam ederse internet "
                  "bağlantınızı kontrol edin veya farklı bir ağ deneyin.\n"
                  "  → /retry ile tekrar dene",
    },
    FailoverReason.AUTH: {
        "title": "🔑 Kimlik Doğrulama Hatası",
        "what": "API anahtarı geçersiz, süresi dolmuş veya yetkisiz erişim.",
        "why": "API anahtarınız yanlış olabilir, süresi dolmuş olabilir veya bu endpoint'e "
               "erişim yetkiniz olmayabilir.",
        "action": "API anahtarınızı kontrol edin veya yenileyin.\n"
                  "  → /setup ile API anahtarlarını güncelle\n"
                  "  → /keys ile mevcut anahtarları görüntüle",
    },
    FailoverReason.RATE_LIMIT: {
        "title": "⏳ Rate Limit Aşıldı",
        "what": "API'ye çok fazla istek gönderildiği için geçici olarak engellendiniz.",
        "why": "Kısa sürede çok fazla API çağrısı yapıldı. Sağlayıcı rate limit uyguluyor.",
        "action": "Bir süre bekleyip tekrar deneyin. Sistem otomatik olarak alternatif "
                  "bir sağlayıcıya geçmeyi deneyecek.\n"
                  "  → /retry ile tekrar dene (otomatik fallback)",
    },
    FailoverReason.TIMEOUT: {
        "title": "⏱️ Zaman Aşımı",
        "what": "API isteği çok uzun sürdü ve zaman aşımına uğradı.",
        "why": "Sunucu yavaş yanıt veriyor olabilir, istek çok büyük olabilir veya "
               "ağ bağlantınızda gecikme olabilir.",
        "action": "Daha kısa bir sorgu ile tekrar deneyin veya bekleyip tekrar deneyin.\n"
                  "  → /retry ile tekrar dene",
    },
    FailoverReason.TOOL_ERROR: {
        "title": "🔧 Araç (Tool) Hatası",
        "what": "Bir araç çalıştırılırken hata oluştu.",
        "why": "Araca geçersiz parametreler gönderilmiş olabilir, araç geçici olarak "
               "çalışmıyor olabilir veya izin hatası olabilir.",
        "action": "Parametreleri kontrol edin. Eğer izin hatası ise gerekli izinleri "
                  "verin.\n"
                  "  → Farklı parametrelerle tekrar dene\n"
                  "  → /help ile kullanılabilir araçları gör",
    },
    FailoverReason.PARSE_ERROR: {
        "title": "📄 Ayrıştırma (Parse) Hatası",
        "what": "API'den gelen yanıt beklenen formatta değil.",
        "why": "API değişmiş olabilir, model hatalı format üretmiş olabilir veya "
               "iletişim sırasında veri bozulmuş olabilir.",
        "action": "Sistem otomatik olarak tekrar deneyecek. Eğer sorun devam ederse "
                  "farklı bir model kullanmayı deneyin.\n"
                  "  → /retry ile tekrar dene\n"
                  "  → /model ile farklı model seç",
    },
    FailoverReason.UNKNOWN: {
        "title": "❓ Bilinmeyen Hata",
        "what": "Beklenmeyen bir hata oluştu.",
        "why": "Nedeni tespit edilemedi. Geçici bir sorun olabilir.",
        "action": "İşlemi tekrar deneyin. Sorun devam ederse /new ile yeni bir "
                  "oturum başlatın.\n"
                  "  → /retry ile tekrar dene\n"
                  "  → /new ile yeni oturum",
    },
}


def format_user_error(
    error: Exception | ClassifiedError | str,
    *,
    provider: str = "",
    model: str = "",
) -> str:
    """Kullanıcıya anlamlı hata mesajı formatla.

    Args:
        error: ClassifiedError, Exception veya string hata mesajı
        provider: API sağlayıcı adı
        model: Model adı

    Returns:
        Kullanıcıya gösterilecek formatlı hata mesajı (Markdown)
    """
    from core.logger import log

    # ClassifiedError ise doğrudan kullan
    if isinstance(error, ClassifiedError):
        classified = error
    elif isinstance(error, Exception):
        classified = classify_api_error(error, provider=provider, model=model)
    else:
        # String -> classify et
        exc = Exception(str(error))
        classified = classify_api_error(exc, provider=provider, model=model)

    msg_data = ERROR_USER_MESSAGES.get(
        classified.reason,
        ERROR_USER_MESSAGES[FailoverReason.UNKNOWN],
    )

    # Provider/model bilgisi varsa ekle
    provider_info = ""
    if provider or model:
        provider_info = f"\n\n**Sağlayıcı:** {provider or '-'}  |  **Model:** {model or '-'}"

    header = msg_data["title"]
    if classified.status_code:
        header += f" (HTTP {classified.status_code})"

    return (
        f"{header}\n\n"
        f"**Ne oldu?** {msg_data['what']}\n\n"
        f"**Neden oldu?** {msg_data['why']}\n\n"
        f"**Ne yapmalı?** {msg_data['action']}"
        f"{provider_info}"
    )
