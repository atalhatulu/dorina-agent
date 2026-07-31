"""Web content scraping with httpx."""

from __future__ import annotations
from core.logger import log


def _sanitize(text: str) -> str:
    """Sanitize scraped content against prompt injection."""
    try:
        from tools.security import sanitize_external_content
        return sanitize_external_content(text)
    except (ImportError, AttributeError):
        return text


class WebScraper:
    """Fetch content from URL."""

    def fetch_sync(self, url: str, timeout: int = 15) -> str | None:
        """Fetch content from URL (sync)."""
        import httpx
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; DorinaAgent/2.0)"})
            resp.raise_for_status()
            if "text/html" in resp.headers.get("content-type", ""):
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                text = soup.get_text(separator="\n", strip=True)
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                return "\n".join(lines[:200])
            return resp.text[:5000]
        except (httpx.RequestError, OSError) as e:
            return None

    async def fetch(self, url: str, timeout: int = 15) -> str | None:
        """Fetch text content from URL."""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; DorinaAgent/2.0)"
                    },
                )
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")

                if "text/html" in content_type:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(resp.text, "html.parser")

                    # Remove script/style tags
                    for tag in soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()

                    text = soup.get_text(separator="\n", strip=True)
                    lines = [line.strip() for line in text.split("\n") if line.strip()]
                    result = "\n".join(lines[:200])  # First 200 lines
                    return _sanitize(result)

                elif "application/json" in content_type:
                    return _sanitize(resp.text[:5000])

                else:
                    return _sanitize(resp.text[:5000])

        except (httpx.RequestError, OSError) as e:
            log.error(f"Web scraping error [{url}]: {e}")
            return None


scraper = WebScraper()
