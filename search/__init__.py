"""Search engine — DuckDuckGo (fallback) + Google Custom Search (opsiyonel).

Kullanım:
    from search.engine import search_engine

    results = search_engine.search("python ai")
    for r in results.results:
        print(r.title, r.url)
"""

from .engine import (
    SearchEngine,
    SearchProvider,
    SearchResult,
    SearchResponse,
    DuckDuckGoProvider,
    GoogleCustomSearchProvider,
    search_engine,
)

__all__ = [
    "SearchEngine",
    "SearchProvider",
    "SearchResult",
    "SearchResponse",
    "DuckDuckGoProvider",
    "GoogleCustomSearchProvider",
    "search_engine",
]
