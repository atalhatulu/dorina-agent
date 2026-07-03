"""Web search engine — DuckDuckGo with multi-engine support."""

from __future__ import annotations
from typing import Optional

from core.logger import log


class WebSearch:
    """Web search engine. DuckDuckGo with multi-engine support.

    Integration points:
      - deep_research.py: Used for parallel search
      - rag_engine.py: Used to append research results
      - tools/builtin/modules.py: web_search tool uses this class
    """

    def __init__(self):
        self._search = None
        self.cache: dict[str, list[dict]] = {}

    def _init(self):
        if self._search is None:
            try:
                from ddgs import DDGS
                self._search = DDGS()
            except ImportError:
                log.debug("ddgs (duckduckgo_search) not loaded, using web_fetch fallback")
                self._search = False

    def search_web(
        self,
        query: str,
        max_results: int = 5,
        safesearch: str = "on",
        region: str = "wt-wt",
        use_cache: bool = True,
    ) -> list[dict]:
        """Search the web, return results.

        Args:
            query: Search query
            max_results: Maximum result count
            safesearch: Safe search ("on", "off", "moderate")
            region: Region code ("wt-wt", "tr-tr", "en-us", etc.)
            use_cache: Use cache if available

        Returns:
            List of dicts, each with {"title", "url", "snippet", "source"}
        """
        cache_key = f"{query}:{max_results}:{region}"
        if use_cache and cache_key in self.cache:
            return self.cache[cache_key]

        self._init()
        if not self._search:
            return []

        try:
            results = list(
                self._search.text(
                    query,
                    max_results=max_results,
                    safesearch=safesearch,
                    region=region,
                )
            )
            formatted = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "source": "duckduckgo",
                }
                for r in results
            ]
            self.cache[cache_key] = formatted
            return formatted
        except (TimeoutError, OSError, ValueError) as e:
            log.error(f"Web search error: {e}")
            return []

    def search_news(self, query: str, max_results: int = 5) -> list[dict]:
        """Search news."""
        self._init()
        if not self._search:
            return []

        try:
            results = list(self._search.news(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "date": r.get("date", ""),
                    "source": "duckduckgo_news",
                }
                for r in results
            ]
        except (TimeoutError, OSError, ValueError) as e:
            log.error(f"Web news search error: {e}")
            return []

    def search_multi(
        self, query: str, max_results: int = 5
    ) -> list[dict]:
        """Multi-engine search (web + news)."""
        web_results = self.search_web(query, max_results=max_results)
        news_results = self.search_news(query, max_results=max_results // 2)
        combined = web_results + news_results
        # Remove duplicates by URL
        seen = set()
        unique = []
        for r in combined:
            url = r.get("url", "")
            if url and url not in seen:
                seen.add(url)
                unique.append(r)
        return unique[:max_results]

    def clear_cache(self):
        """Clear search cache."""
        self.cache.clear()


web_search = WebSearch()
