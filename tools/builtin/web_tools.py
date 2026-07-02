"""Web tools — search and fetch."""

from __future__ import annotations
import asyncio
import json

from tools.registry import register_tool
from core.utils import safe_json_loads
from core.logger import log


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

    except (httpx.HTTPError, TimeoutError, OSError, json.JSONDecodeError, ImportError) as e:
        _err_msg = str(e)
        _error_info = " (muhtemelen Google/DDG engelledi)"

        # Alternatif: web_fetch ile dogrudan ara
        try:
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
        except (httpx.HTTPError, OSError, json.JSONDecodeError, ImportError):
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
        except (httpx.RequestError, TimeoutError, OSError) as e:
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
            except (json.JSONDecodeError, TypeError, AttributeError):
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
            except (ImportError, AttributeError, TypeError):
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
