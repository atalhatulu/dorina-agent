"""Web browser — Playwright Async API ile sayfa gezme, tıklama, form, kaydırma, metin çekme.

Async API (playwright.async_api) kullanılır. Global bir browser instance'ı
tüm çağrılar arasında paylaşılır, böylece sync/async çakışması olmaz.
"""
from __future__ import annotations
import asyncio
from pathlib import Path
from typing import Optional
from core.logger import log


class AsyncBrowserClient:
    """Playwright Async API ile browser kontrolü.

    _ensure() her tool çağrısında lazily browser'ı başlatır.
    Browser instance'ı global düzeyde singleton olarak tutulur.
    """

    def __init__(self):
        self._page = None
        self._browser = None
        self._playwright = None
        self.available = False

    async def _ensure(self):
        """Browser instance'ını async olarak başlat (lazy)."""
        if self._page is not None:
            return
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            self._page = await self._browser.new_page()
            self.available = True
            log.info("Browser (async) baslatildi")
        except Exception as e:
            log.warning(f"Browser baslatilamadi: {e}")

    async def navigate(self, url: str) -> str:
        """Sayfaya git. URL scheme yoksa https:// ekle."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor (playwright kurulu degil)"
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            await self._page.goto(url, timeout=15000, wait_until="domcontentloaded")
            title = await self._page.title()
            return f"Sayfa yuklendi: {title} ({url})"
        except Exception as e:
            return f"Sayfa yuklenemedi: {e}"

    # ── Screenshot ──────────────────────────────────────────────
    async def screenshot(self, path: str = "") -> str:
        """Ekran görüntüsü al. Varsayılan: /tmp/dorina_screenshot.png"""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            path = path or "/tmp/dorina_screenshot.png"
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(p))
            return f"Ekran goruntusu kaydedildi: {path}"
        except Exception as e:
            return f"Ekran goruntusu alinamadi: {e}"

    async def screenshot_save(self, path: str = "/tmp/dorina_screenshot.png",
                               full_page: bool = False, format: str = "png") -> str:
        """Gelişmiş ekran görüntüsü — tam sayfa, format seçeneği ile."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        valid_formats = {"png", "jpeg"}
        fmt = format.lower() if format.lower() in valid_formats else "png"
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            await self._page.screenshot(path=str(p), full_page=full_page)
            size = p.stat().st_size if p.exists() else 0
            return f"Ekran goruntusu kaydedildi: {path} (full_page={full_page}, format={fmt}, {size}B)"
        except Exception as e:
            return f"Ekran goruntusu alinamadi: {e}"

    # ── Click ───────────────────────────────────────────────────
    async def click(self, selector: str) -> str:
        """CSS seçici ile tıkla."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.click(selector, timeout=5000)
            return f"Tiklandi (css): {selector}"
        except Exception as e:
            return f"Tiklanamadi: {e}"

    async def click_by_text(self, text: str, exact: bool = True) -> str:
        """Görünür metin içeriğine göre tıkla (Playwright text= seçici)."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            if exact:
                selector = f'text="{text}"'
            else:
                selector = f"text={text}"
            await self._page.click(selector, timeout=5000)
            return f"Tiklandi (text): {text}"
        except Exception as e:
            return f"Metinle tiklanamadi ('{text}'): {e}"

    # ── Form / Fill ─────────────────────────────────────────────
    async def fill(self, selector: str, text: str) -> str:
        """CSS seçici ile input alanını doldur."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.fill(selector, text)
            return f"Dolduruldu: {selector} = {text}"
        except Exception as e:
            return f"Doldurulamadi: {e}"

    async def form_fill(self, field_map: dict[str, str]) -> str:
        """Birden çok alanı tek seferde doldur. {seçici: değer} sözlüğü."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
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
            parts.append(f"Doldurulan({len(filled)}): {', '.join(filled)}")
        if errors:
            parts.append(f"Hata({len(errors)}): {'; '.join(errors)}")
        return " | ".join(parts) if parts else "Form doldurulamadi"

    async def select_option(self, selector: str, value: Optional[str] = None,
                             label: Optional[str] = None) -> str:
        """Select/option elemanından seçim yap."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            if value:
                await self._page.select_option(selector, value=value)
                return f"Secildi (value): {selector}={value}"
            elif label:
                await self._page.select_option(selector, label=label)
                return f"Secildi (label): {selector}={label}"
            else:
                return "Select icin value veya label gerekli"
        except Exception as e:
            return f"Secim yapilamadi: {e}"

    # ── Text Extraction ─────────────────────────────────────────
    async def get_text(self) -> str:
        """Sayfadaki tüm görünür metni döndür (maks 10K karakter)."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            text = await self._page.inner_text("body")
            return text[:10000]
        except Exception as e:
            log.warning(f"Metin alma hatasi: {e}")
            return ""

    async def extract_text(self, selector: str = "body", max_chars: int = 10000) -> str:
        """Belirli bir CSS seçiciden metin çek."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            elements = await self._page.query_selector_all(selector)
            if not elements:
                return f"'{selector}' ile eslesen eleman bulunamadi"
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
            return f"Metin cikarilamadi: {e}"

    async def get_title(self) -> str:
        """Sayfa başlığını döndür."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            return await self._page.title()
        except Exception:
            return ""

    async def get_url(self) -> str:
        """Mevcut sayfa URL'ini döndür."""
        await self._ensure()
        if not self._page:
            return ""
        try:
            return self._page.url
        except Exception:
            return ""

    # ── Scroll ──────────────────────────────────────────────────
    async def scroll(self, delta_x: int = 0, delta_y: int = 300) -> str:
        """Sayfayı kaydır. delta_y > 0 aşağı, < 0 yukarı."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.evaluate(f"window.scrollBy({delta_x}, {delta_y})")
            direction = "asagi" if delta_y > 0 else "yukari" if delta_y < 0 else "yatay"
            return f"Sayfa kaydirildi ({direction}): dx={delta_x}, dy={delta_y}"
        except Exception as e:
            return f"Kaydirma hatasi: {e}"

    async def scroll_to(self, x: int = 0, y: int = 0) -> str:
        """Belirli bir pixel konumuna scroll yap."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.evaluate(f"window.scrollTo({x}, {y})")
            return f"Sayfa konumlandirildi: ({x}, {y})"
        except Exception as e:
            return f"Konumlandirma hatasi: {e}"

    async def scroll_to_bottom(self) -> str:
        """Sayfanın en altına scroll yap."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return "Sayfa en alta kaydirildi"
        except Exception as e:
            return f"En alta kaydirma hatasi: {e}"

    async def scroll_to_top(self) -> str:
        """Sayfanın en üstüne scroll yap."""
        await self._ensure()
        if not self._page:
            return "Browser kullanilamiyor"
        try:
            await self._page.evaluate("window.scrollTo(0, 0)")
            return "Sayfa en uste kaydirildi"
        except Exception as e:
            return f"En uste kaydirma hatasi: {e}"

    # ── Utility ──────────────────────────────────────────────────
    async def close(self):
        """Browser'ı kapat."""
        if self._browser:
            try:
                await self._browser.close()
            except Exception as e:
                log.warning(f"Browser kapatma hatasi: {e}")
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception as e:
                log.warning(f"Playwright durdurma hatasi: {e}")
        self._page = None
        self._browser = None
        self._playwright = None
        self.available = False
        log.info("Browser kapandi")


# Global async browser singleton
browser = AsyncBrowserClient()
