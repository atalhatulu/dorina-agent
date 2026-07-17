"""Web browser — Playwright Async API: navigate, click, fill, scroll, extract text.

Uses playwright.async_api. A global browser instance is shared across calls.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional
from core.logger import log


class AsyncBrowserClient:
    """Async browser control via Playwright.

    _ensure() lazily starts the browser on each tool call.
    Browser instance is held as a global singleton.
    """

    def __init__(self):
        self._page = None
        self._browser = None
        self._playwright = None
        self.available = False

    async def _ensure(self):
        """Lazily start the browser instance (async)."""
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
            self.available = True
            log.info("Browser (async) started")
        except Exception as e:
            log.warning(f"Browser failed to start: {e}")

    async def navigate(self, url: str) -> str:
        """Navigate to a URL. Adds https:// if no scheme is present."""
        await self._ensure()
        if not self._page:
            return "Browser not available (playwright not installed)"
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await self._page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = await self._page.title()
            return f"Page loaded: {title} ({url})"
        except Exception as e:
            return f"Page could not be loaded: {e}"

    # ── Screenshot ──────────────────────────────────────────────
    async def screenshot(self, path: str = "") -> str:
        """Take a screenshot. Default: /tmp/dorina_screenshot.png"""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            path = path or "/tmp/dorina_screenshot.png"
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(p))
            return f"Screenshot saved: {path}"
        except Exception as e:
            return f"Screenshot failed: {e}"

    async def screenshot_save(self, path: str = "/tmp/dorina_screenshot.png",
                               full_page: bool = False, format: str = "png") -> str:
        """Advanced screenshot — full page support, format option."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        valid_formats = {"png", "jpeg"}
        fmt = format.lower() if format.lower() in valid_formats else "png"
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(p), full_page=full_page)
            size = p.stat().st_size if p.exists() else 0
            return f"Screenshot saved: {path} (full_page={full_page}, format={fmt}, {size}B)"
        except Exception as e:
            return f"Screenshot failed: {e}"

    # ── Click ───────────────────────────────────────────────────
    async def click(self, selector: str) -> str:
        """Click an element by CSS selector."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.click(selector, timeout=5000)
            return f"Clicked (css): {selector}"
        except Exception as e:
            return f"Could not click: {e}"

    async def click_by_text(self, text: str, exact: bool = True) -> str:
        """Click an element by its visible text (Playwright text= selector)."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            if exact:
                selector = f'text="{text}"'
            else:
                selector = f"text={text}"
            await self._page.click(selector, timeout=5000)
            return f"Clicked (text): {text}"
        except Exception as e:
            return f"Could not click by text ('{text}'): {e}"

    # ── Form / Fill ─────────────────────────────────────────────
    async def fill(self, selector: str, text: str) -> str:
        """Fill an input field by CSS selector."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.fill(selector, text)
            return f"Filled: {selector} = {text}"
        except Exception as e:
            return f"Could not fill: {e}"

    async def form_fill(self, field_map: dict[str, str]) -> str:
        """Fill multiple fields at once. {selector: value} dictionary."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        filled = []
        errors = []
        for selector, value in field_map.items():
            try:
                await self._page.fill(selector, value)
                filled.append(selector)
            except Exception as e:
                errors.append(f"{selector}: {e}")
        parts = []
        if filled:
            parts.append(f"Filled({len(filled)}): {', '.join(filled)}")
        if errors:
            parts.append(f"Errors({len(errors)}): {'; '.join(errors)}")
        return " | ".join(parts) if parts else "Form could not be filled"

    async def select_option(self, selector: str, value: Optional[str] = None,
                             label: Optional[str] = None) -> str:
        """Select an option from a select/option element."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            if value:
                await self._page.select_option(selector, value=value)
                return f"Selected (value): {selector}={value}"
            elif label:
                await self._page.select_option(selector, label=label)
                return f"Selected (label): {selector}={label}"
            else:
                return "Select requires value or label"
        except Exception as e:
            return f"Could not select: {e}"

    # ── Text Extraction ─────────────────────────────────────────
    async def get_text(self) -> str:
        """Return all visible text on the page (max 10K chars)."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            text = await self._page.inner_text("body")
            return text[:10000]
        except (TimeoutError, AttributeError) as e:
            log.warning(f"Text extraction error: {e}")
            return ""

    async def extract_text(self, selector: str = "body", max_chars: int = 10000) -> str:
        """Extract text from a specific CSS selector."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            elements = await self._page.query_selector_all(selector)
            if not elements:
                return f"No elements matched '{selector}'"
            texts = []
            total = 0
            for el in elements:
                t = await el.inner_text()
                if total + len(t) > max_chars:
                    t = t[: max_chars - total]
                texts.append(t)
                total += len(t)
                if total >= max_chars:
                    break
            return "\n---\n".join(texts)
        except Exception as e:
            return f"Could not extract text: {e}"

    async def get_title(self) -> str:
        """Return the page title."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            return await self._page.title()
        except (TimeoutError, AttributeError):
            return ""

    async def get_url(self) -> str:
        """Return the current page URL."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            return self._page.url
        except (TimeoutError, AttributeError):
            return ""

    # ── Scroll ──────────────────────────────────────────────────
    async def scroll(self, delta_x: int = 0, delta_y: int = 300) -> str:
        """Scroll the page. delta_y > 0 = down, < 0 = up."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
            direction = "down" if delta_y > 0 else "up" if delta_y < 0 else "horizontal"
            return f"Scrolled ({direction}): dx={delta_x}, dy={delta_y}"
        except Exception as e:
            return f"Scroll error: {e}"

    async def scroll_to(self, x: int = 0, y: int = 0) -> str:
        """Scroll to a specific pixel position."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.evaluate(f"window.scrollTo({x}, {y})")
            return f"Scrolled to: ({x}, {y})"
        except Exception as e:
            return f"Scroll-to error: {e}"

    async def scroll_to_bottom(self) -> str:
        """Scroll to the bottom of the page."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return "Scrolled to bottom"
        except Exception as e:
            return f"Scroll-to-bottom error: {e}"

    async def scroll_to_top(self) -> str:
        """Scroll to the top of the page."""
        await self._ensure()
        if not self._page:
            return "Browser not available"
        try:
            await self._page.evaluate("window.scrollTo(0, 0)")
            return "Scrolled to top"
        except Exception as e:
            return f"Scroll-to-top error: {e}"

    # ── Utility ──────────────────────────────────────────────────
    async def close(self):
        """Close the browser."""
        if self._browser:
            try:
                await self._browser.close()
            except (TimeoutError, AttributeError) as e:
                log.warning(f"Browser close error: {e}")
        if self._playwright:
            try:
                await self._playwright.stop()
            except (TimeoutError, AttributeError) as e:
                log.warning(f"Playwright stop error: {e}")
        self._page = None
        self._browser = None
        self._playwright = None
        self.available = False
        log.info("Browser closed")


# Global async browser singleton
browser = AsyncBrowserClient()

# Register cleanup on exit
import atexit
atexit.register(lambda: asyncio.run(browser.close()) if browser.available else None)
