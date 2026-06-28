"""Web içerik çekme - httpx ile."""

from __future__ import annotations
from core.logger import log


class WebScraper:
    """URL'den içerik çek."""

    def fetch_sync(self, url: str, timeout: int = 15) -> str | None:
        """URLden içerik çek (sync)."""
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
        except Exception as e:
            return None

    async def fetch(self, url: str, timeout: int = 15) -> str | None:
        """URL'den metin içerik çek."""
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
                    return "\n".join(lines[:200])  # İlk 200 satır

                elif "application/json" in content_type:
                    return resp.text[:5000]
                
                else:
                    return resp.text[:5000]

        except Exception as e:
            log.error(f"Web çekme hatası [{url}]: {e}")
            return None


scraper = WebScraper()
