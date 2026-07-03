"""API error classification — Hermes-inspired error taxonomy.

Categorizes LLM API errors into structured recovery actions:
retry, rotate credential, fallback, compress context, or abort.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Any

from core.constants import get_language


class FailoverReason:
    """API error categories — determines recovery strategy."""
    AUTH = "auth"
    AUTH_PERMANENT = "auth_permanent"
    BILLING = "billing"
    RATE_LIMIT = "rate_limit"
    UPSTREAM_RATE_LIMIT = "upstream_rate_limit"  # API key saglikli, upstream provider limitli
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
    "insufficient balance", "credit balance", "credits exhausted",
    "credits have been exhausted", "no usable credits", "top up your credits",
    "payment required", "billing hard limit", "exceeded your current quota",
    "out of funds", "balance_depleted", "quota exceeded",
    "account is deactivated", "plan does not include",
    "out of extra usage", "run out of funds",
    "model_not_supported_on_free_tier", "not available on the free tier",
]

_RATE_LIMIT_PATTERNS = [
    "rate limit", "rate_limit", "too many requests", "throttled",
    "requests per minute", "tokens per minute", "requests per day",
    "try again in", "please retry after", "resource_exhausted", "429",
    "rate increased too quickly",
    "throttlingexception", "too many concurrent requests",
    "servicequotaexceededexception",
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
    "overloaded", "temporarily overloaded",
    "service is temporarily overloaded", "service may be temporarily overloaded",
    "server is overloaded", "server overloaded", "service overloaded",
    "service is overloaded", "upstream overloaded",
    "currently overloaded", "at capacity", "over capacity",
    "503", "529", "service unavailable",
    "temporarily unavailable", "capacity",
]

_SERVER_ERROR_PATTERNS = [
    "500", "502", "internal server error", "server error",
    "bad gateway", "gateway timeout",
]

# Upstream provider rate-limited (aggregator 429) — model fallback, NOT credential rotate
_UPSTREAM_RATE_LIMIT_PATTERNS = [
    "upstream rate limit", "upstream_rate_limit",
    "provider returned error", "upstream provider",
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
        (FailoverReason.UPSTREAM_RATE_LIMIT, _UPSTREAM_RATE_LIMIT_PATTERNS, True, False, True),
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
            # upstream_rate_limit: model fallback, NOT credential rotate
            if reason == FailoverReason.UPSTREAM_RATE_LIMIT:
                c.should_rotate_credential = False
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

ERROR_USER_MESSAGES_TR: dict[str, dict[str, str]] = {
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
    FailoverReason.UPSTREAM_RATE_LIMIT: {
        "title": "⏳ Upstream Rate Limiti",
        "what": "API sağlayıcının upstream model sağlayıcısı rate limit uyguluyor.",
        "why": "Bu genellikle OpenRouter gibi aggregator'lar aracılığıyla kullanılan "
               "modellerde olur. Kendi API anahtarınız sağlıklı, upstream sağlayıcı limitli.",
        "action": "Sistem otomatik olarak farklı bir modele geçmeyi deneyecek.\n"
                  "  → /retry ile tekrar dene\n"
                  "  → /model ile farklı model seç",
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

ERROR_USER_MESSAGES_EN: dict[str, dict[str, str]] = {
    FailoverReason.TOOL_FORMAT_ERROR: {
        "title": "🔧 Message Order Error",
        "what": "The message order between the tool call and its result was corrupted.",
        "why": "This typically happens when Ctrl+C interrupts a tool operation, or an unexpected "
               "message appears between the assistant's tool_calls and the tool result. "
               "Models like DeepSeek require strict assistant(tool_calls) → tool message ordering.",
        "action": "The system automatically repaired the message order and is retrying. "
                  "This usually resolves in a few seconds.\n"
                  "  → Use /retry to try again manually\n"
                  "  → Use /new to start a fresh session",
    },
    FailoverReason.NETWORK: {
        "title": "🌐 Network Error",
        "what": "Could not connect to the API server or the connection was lost.",
        "why": "Your internet connection may be unstable, the API service may be temporarily "
               "down, or there may be a DNS/proxy issue.",
        "action": "Wait a few seconds and try again. If the problem persists, check your "
                  "internet connection or try a different network.\n"
                  "  → Use /retry to try again",
    },
    FailoverReason.AUTH: {
        "title": "🔑 Authentication Error",
        "what": "The API key is invalid, expired, or unauthorized.",
        "why": "Your API key may be incorrect, expired, or you may not have permission "
               "for this endpoint.",
        "action": "Check or renew your API key.\n"
                  "  → Use /setup to update API keys\n"
                  "  → Use /keys to view current keys",
    },
    FailoverReason.RATE_LIMIT: {
        "title": "⏳ Rate Limit Exceeded",
        "what": "Temporarily blocked for sending too many requests to the API.",
        "why": "Too many API calls were made in a short period. The provider enforces rate limits.",
        "action": "Wait a while and try again. The system will automatically attempt to "
                  "fall back to an alternative provider.\n"
                  "  → Use /retry to try again (auto fallback)",
    },
    FailoverReason.UPSTREAM_RATE_LIMIT: {
        "title": "⏳ Upstream Rate Limit",
        "what": "The upstream model provider is enforcing a rate limit on the API provider.",
        "why": "This typically happens when using aggregators like OpenRouter. "
               "Your own API key is valid, but the upstream provider is rate-limited.",
        "action": "The system will automatically attempt to switch to a different model.\n"
                  "  → Use /retry to try again\n"
                  "  → Use /model to pick a different model",
    },
    FailoverReason.TIMEOUT: {
        "title": "⏱️ Timeout Error",
        "what": "The API request took too long and timed out.",
        "why": "The server may be responding slowly, the request may be too large, "
               "or there may be network latency.",
        "action": "Try again with a shorter query or wait before retrying.\n"
                  "  → Use /retry to try again",
    },
    FailoverReason.TOOL_ERROR: {
        "title": "🔧 Tool Error",
        "what": "An error occurred while executing a tool.",
        "why": "Invalid parameters may have been sent to the tool, the tool may be "
               "temporarily unavailable, or there may be a permission error.",
        "action": "Check the parameters. If it's a permission error, grant the "
                  "necessary permissions.\n"
                  "  → Try with different parameters\n"
                  "  → Use /help to see available tools",
    },
    FailoverReason.PARSE_ERROR: {
        "title": "📄 Parse Error",
        "what": "The API response was not in the expected format.",
        "why": "The API may have changed, the model may have produced a malformed response, "
               "or data may have been corrupted during transmission.",
        "action": "The system will automatically retry. If the problem persists, try "
                  "using a different model.\n"
                  "  → Use /retry to try again\n"
                  "  → Use /model to pick a different model",
    },
    FailoverReason.UNKNOWN: {
        "title": "❓ Unknown Error",
        "what": "An unexpected error occurred.",
        "why": "The cause could not be determined. It may be a temporary issue.",
        "action": "Try again. If the problem persists, start a new session with /new.\n"
                  "  → Use /retry to try again\n"
                  "  → Use /new to start a fresh session",
    },
}


def _get_error_message(reason: str) -> dict[str, str]:
    """Return user-facing error message dict in the active language."""
    if get_language() == "tr":
        return ERROR_USER_MESSAGES_TR.get(
            reason, ERROR_USER_MESSAGES_TR[FailoverReason.UNKNOWN]
        )
    return ERROR_USER_MESSAGES_EN.get(
        reason, ERROR_USER_MESSAGES_EN[FailoverReason.UNKNOWN]
    )


def format_user_error(
    error: Exception | ClassifiedError | str,
    *,
    provider: str = "",
    model: str = "",
) -> str:
    """Format a user-friendly error message in the active language.

    Args:
        error: ClassifiedError, Exception, or error string
        provider: API provider name
        model: Model name

    Returns:
        Formatted error message (Markdown)
    """
    from core.logger import log

    # Use directly if already classified
    if isinstance(error, ClassifiedError):
        classified = error
    elif isinstance(error, Exception):
        classified = classify_api_error(error, provider=provider, model=model)
    else:
        exc = Exception(str(error))
        classified = classify_api_error(exc, provider=provider, model=model)

    msg_data = _get_error_message(classified.reason)

    is_en = get_language() != "tr"
    # Add provider/model info if available
    provider_info = ""
    if provider or model:
        if is_en:
            provider_info = f"\n\n**Provider:** {provider or '-'}  |  **Model:** {model or '-'}"
        else:
            provider_info = f"\n\n**Provider:** {provider or '-'}  |  **Model:** {model or '-'}"

    header = msg_data["title"]
    if classified.status_code:
        header += f" (HTTP {classified.status_code})"

    if is_en:
        return (
            f"{header}\n\n"
            f"**What happened?** {msg_data['what']}\n\n"
            f"**Why?** {msg_data['why']}\n\n"
            f"**What to do?** {msg_data['action']}"
            f"{provider_info}"
        )
    return (
        f"{header}\n\n"
        f"**Ne oldu?** {msg_data['what']}\n\n"
        f"**Neden oldu?** {msg_data['why']}\n\n"
        f"**What to do:** {msg_data['action']}"
        f"{provider_info}"
    )
