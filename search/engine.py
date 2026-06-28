"""Search engine — provider abstraction with Strategy pattern.

DuckDuckGo (varsayılan fallback) + Google Custom Search API (opsiyonel) desteği.
Arama sonuçlarını yapılandırılmış formata çevirir.

Kullanım:
    from search.engine import search_engine

    # DuckDuckGo (default)
    results = search_engine.search("python ai agent")

    # Google Custom Search (API key ayarlanmışsa)
    results = search_engine.search("python ai agent", provider="google")
"""

from __future__ import annotations
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional
from urllib.parse import quote_plus, urlencode

from core.logger import log
from core.config import settings


# ── Structured Result Format ────────────────────────────────────


@dataclass
class SearchResult:
    """Yapılandırılmış arama sonucu."""
    title: str = ""
    url: str = ""
    snippet: str = ""
    source: str = ""  # "duckduckgo", "google", etc.
    position: int = 0
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchResponse:
    """Structured search response with metadata."""
    query: str = ""
    results: list[SearchResult] = field(default_factory=list)
    total: int = 0
    provider: str = ""
    error: Optional[str] = None
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "results": [r.to_dict() for r in self.results],
            "total": self.total,
            "provider": self.provider,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def to_text(self, max_results: int = 5) -> str:
        """Sonuçları okunabilir metin formatında döndür."""
        if self.error:
            return f"Search error: {self.error}"
        if not self.results:
            return f"No results found for '{self.query}'."
        lines = [f"Search results for '{self.query}' (via {self.provider}):\n"]
        for r in self.results[:max_results]:
            lines.append(f"  {r.position}. {r.title}")
            lines.append(f"     {r.url}")
            if r.snippet:
                lines.append(f"     {r.snippet[:200]}")
            lines.append("")
        return "\n".join(lines)


# ── Provider Interface (Strategy Pattern) ──────────────────────


class SearchProvider(ABC):
    """Abstract search provider — Strategy pattern interface."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    def _make_response(
        self,
        query: str,
        results: list[SearchResult],
        elapsed_ms: float,
        error: str = None,
    ) -> SearchResponse:
        return SearchResponse(
            query=query,
            results=results,
            total=len(results),
            provider=self.name,
            error=error,
            elapsed_ms=elapsed_ms,
        )


# ── DuckDuckGo Provider (Fallback) ─────────────────────────────


class DuckDuckGoProvider(SearchProvider):
    """DuckDuckGo search provider — default fallback.

    Uses ddgs (DuckDuckGo Search) library.
    """

    @property
    def name(self) -> str:
        return "duckduckgo"

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.time()
        try:
            from ddgs import DDGS  # type: ignore

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=max_results))

            results = []
            for i, r in enumerate(raw_results):
                results.append(SearchResult(
                    title=r.get("title", ""),
                    url=r.get("href", r.get("url", "")),
                    snippet=r.get("body", r.get("snippet", "")),
                    source=self.name,
                    position=i + 1,
                ))

            elapsed = (time.time() - start) * 1000
            log.debug(f"DuckDuckGo search '{query[:40]}': {len(results)} results in {elapsed:.0f}ms")
            return self._make_response(query, results, elapsed)

        except ImportError:
            error = "ddgs library not installed. Install: pip install ddgs"
            log.error(error)
            return self._make_response(query, [], 0, error=error)
        except Exception as e:
            error = f"DuckDuckGo search failed: {e}"
            log.warning(error)
            return self._make_response(query, [], 0, error=error)


# ── Google Custom Search Provider ──────────────────────────────


class GoogleCustomSearchProvider(SearchProvider):
    """Google Custom Search API provider — opsiyonel.

    Requires:
        - GOOGLE_API_KEY env var or config
        - GOOGLE_CSE_ID env var or config (Custom Search Engine ID)
    """

    @property
    def name(self) -> str:
        return "google"

    def _get_api_key(self) -> str | None:
        """Get Google API key from config or env."""
        try:
            key = getattr(settings, "google_api_key", None) or settings.api_keys.get("google")
            if key:
                return key
        except Exception:
            pass
        return os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY")

    def _get_cse_id(self) -> str | None:
        """Get Custom Search Engine ID."""
        return os.getenv("GOOGLE_CSE_ID") or os.getenv("GOOGLE_CX")

    def search(self, query: str, max_results: int = 5) -> SearchResponse:
        start = time.time()

        api_key = self._get_api_key()
        cse_id = self._get_cse_id()

        if not api_key or not cse_id:
            error = (
                "Google Custom Search requires GOOGLE_API_KEY and GOOGLE_CSE_ID "
                "(or GOOGLE_CX) environment variables"
            )
            log.warning(error)
            return self._make_response(query, [], 0, error=error)

        try:
            import httpx

            params = {
                "key": api_key,
                "cx": cse_id,
                "q": query,
                "num": min(max_results, 10),  # Google max 10 per request
            }

            with httpx.Client(timeout=10.0) as client:
                resp = client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()

            items = data.get("items", [])
            search_info = data.get("searchInformation", {})

            results = []
            for i, item in enumerate(items):
                pagemap = item.get("pagemap", {})
                metatags = pagemap.get("metatags", [{}])[0] if pagemap.get("metatags") else {}

                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=self.name,
                    position=i + 1,
                    extra={
                        "displayLink": item.get("displayLink", ""),
                        "formattedUrl": item.get("formattedUrl", ""),
                        "description": metatags.get("og:description", ""),
                    },
                ))

            elapsed = (time.time() - start) * 1000
            total_results = int(search_info.get("totalResults", len(results)))
            log.debug(f"Google search '{query[:40]}': {len(results)}/{total_results} results in {elapsed:.0f}ms")

            resp = self._make_response(query, results, elapsed)
            resp.total = total_results
            return resp

        except httpx.HTTPStatusError as e:
            error = f"Google API HTTP error: {e.response.status_code} - {e.response.text[:200]}"
            log.warning(error)
            return self._make_response(query, [], (time.time() - start) * 1000, error=error)
        except Exception as e:
            error = f"Google search failed: {e}"
            log.warning(error)
            return self._make_response(query, [], (time.time() - start) * 1000, error=error)


# ── Combined Search Engine ─────────────────────────────────────


class SearchEngine:
    """Main search engine — provider selection with fallback.

    Strategy pattern: provider abstraction sayesinde yeni arama motorları
    kolayca eklenebilir. Sadece SearchProvider arayüzünü implemente etmek yeterli.

    Provider seçimi:
      1. Belirtilen provider'ı dene (ör: "google")
      2. Başarısız olursa DuckDuckGo fallback
      3. O da başarısız olursa hata döndür
    """

    def __init__(self):
        self._providers: dict[str, SearchProvider] = {}

        # Register built-in providers
        self.register(DuckDuckGoProvider())
        self.register(GoogleCustomSearchProvider())

        # Default provider
        self._default_provider = "duckduckgo"

    def register(self, provider: SearchProvider):
        """Register a new search provider."""
        self._providers[provider.name] = provider
        log.debug(f"Search provider registered: {provider.name}")

    def get_provider(self, name: str) -> SearchProvider | None:
        """Get a registered provider by name."""
        return self._providers.get(name)

    def list_providers(self) -> list[str]:
        """List all registered provider names."""
        return list(self._providers.keys())

    def search(
        self,
        query: str,
        provider: str = "",
        max_results: int = 5,
    ) -> SearchResponse:
        """Execute a search with automatic fallback.

        Args:
            query: Search query string
            provider: Provider name (e.g., "google", "duckduckgo").
                      Empty string = default provider.
            max_results: Maximum number of results to return.

        Returns:
            SearchResponse with structured results or error info.
        """
        if not query or not query.strip():
            return SearchResponse(
                query=query,
                error="Empty search query",
            )

        query = query.strip()
        provider_name = provider or self._default_provider

        # Try requested provider first
        if provider_name in self._providers:
            log.debug(f"Search: using provider '{provider_name}' for '{query[:40]}'")
            response = self._providers[provider_name].search(query, max_results)
            if response.error is None or provider_name == self._default_provider:
                return response
            log.info(f"Provider '{provider_name}' failed, falling back to DuckDuckGo")

        # Fallback to DuckDuckGo
        if self._default_provider in self._providers:
            log.debug(f"Search fallback: using '{self._default_provider}' for '{query[:40]}'")
            response = self._providers[self._default_provider].search(query, max_results)
            return response

        # No providers available
        return SearchResponse(
            query=query,
            error="No search providers available",
        )

    # ── Backward Compatibility ───────────────────────────────────
    # Old API used by existing tests (list of dicts, add/remove/set providers)

    @property
    def providers(self) -> list[str]:
        """Backward compat: list of provider names."""
        return self.list_providers()

    @providers.setter
    def providers(self, names: list[str]):
        """Backward compat: set providers by name list."""
        # Clear and re-register only those that exist
        existing = dict(self._providers)
        self._providers.clear()
        for n in names:
            if n in existing:
                self._providers[n] = existing[n]
            else:
                # Try to import built-in provider by name
                from importlib import import_module
                try:
                    mod = import_module(f"search.engine")
                    for cls_name in dir(mod):
                        cls = getattr(mod, cls_name)
                        if isinstance(cls, type) and issubclass(cls, SearchProvider) and cls is not SearchProvider:
                            inst = cls()
                            if inst.name == n:
                                self._providers[n] = inst
                                break
                except Exception:
                    pass

    def add_provider(self, name: str):
        """Backward compat: add provider by name (no-op if unknown)."""
        from importlib import import_module
        try:
            mod = import_module("search.engine")
            for cls_name in dir(mod):
                cls = getattr(mod, cls_name)
                if isinstance(cls, type) and issubclass(cls, SearchProvider) and cls is not SearchProvider:
                    inst = cls()
                    if inst.name == name:
                        self.register(inst)
                        return
        except Exception:
            pass

    def remove_provider(self, name: str):
        """Backward compat: remove provider by name."""
        self._providers.pop(name, None)

    def set_providers(self, names: list[str]):
        """Backward compat: set providers."""
        self.providers = names

    def search_parallel(
        self,
        query: str,
        max_results: int = 5,
    ) -> dict[str, SearchResponse]:
        """Search with all available providers in parallel.

        Returns dict mapping provider name → SearchResponse.
        """
        import concurrent.futures

        results = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            future_map = {
                pool.submit(p.search, query, max_results): p.name
                for p in self._providers.values()
            }
            for future in concurrent.futures.as_completed(future_map):
                name = future_map[future]
                try:
                    results[name] = future.result()
                except Exception as e:
                    results[name] = SearchResponse(
                        query=query,
                        error=str(e),
                        provider=name,
                    )
        return results


# Global singleton
search_engine = SearchEngine()
