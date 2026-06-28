"""Tests for browser, gateway, search, vision modules."""
from __future__ import annotations
import sys
import os
import json
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
from PIL import Image


# ═══════════════════════════════════════════════════════════════════
# BROWSER
# ═══════════════════════════════════════════════════════════════════
class TestBrowserClient:
    def test_import(self):
        from browser.client import AsyncBrowserClient
        assert AsyncBrowserClient is not None

    def test_methods_exist(self):
        from browser.client import AsyncBrowserClient
        bc = AsyncBrowserClient()
        expected = [
            "navigate", "screenshot", "screenshot_save",
            "click", "click_by_text", "fill", "form_fill", "select_option",
            "get_text", "get_title", "get_url",
            "scroll", "scroll_to", "close",
        ]
        for m in expected:
            assert hasattr(bc, m), f"Missing method: {m}"

    def test_screenshot_save_no_browser_returns_message(self):
        import asyncio
        from browser.client import AsyncBrowserClient
        bc = AsyncBrowserClient()
        result = asyncio.run(bc.screenshot_save())
        assert isinstance(result, str)
        assert len(result) > 0


# ═══════════════════════════════════════════════════════════════════
# GATEWAY
# ═══════════════════════════════════════════════════════════════════
class TestGatewayServer:
    def test_import(self):
        from gateway.server import gateway, GatewayServer
        assert gateway is not None
        assert isinstance(gateway, GatewayServer)

    def test_methods_exist(self):
        from gateway.server import gateway
        assert hasattr(gateway, "start")
        assert hasattr(gateway, "stop")
        assert hasattr(gateway, "is_running")
        assert hasattr(gateway, "host")
        assert hasattr(gateway, "port")

    def test_start_stop(self):
        """Gateway can be started and stopped without error."""
        from gateway.server import GatewayServer
        g = GatewayServer(port=18642)  # avoid conflict
        msg = g.start()
        assert "Gateway" in msg
        time.sleep(0.3)
        # Can't easily test HTTP from here without background thread lifecycle,
        # but at least start() doesn't crash
        g.stop()
        assert True


# ═══════════════════════════════════════════════════════════════════
# SEARCH
# ═══════════════════════════════════════════════════════════════════
class TestSearchEngine:
    def test_import(self):
        from search.engine import search_engine, SearchEngine
        assert search_engine is not None
        assert isinstance(search_engine, SearchEngine)

    def test_methods_exist(self):
        from search.engine import search_engine
        assert hasattr(search_engine, "search")
        assert hasattr(search_engine, "add_provider")
        assert hasattr(search_engine, "remove_provider")
        assert hasattr(search_engine, "set_providers")
        assert hasattr(search_engine, "providers")

    def test_search_returns_list(self):
        from search.engine import search_engine
        from search.engine import SearchResponse
        results = search_engine.search("pytest python", max_results=3)
        assert isinstance(results, SearchResponse) or isinstance(results, list)
        if isinstance(results, SearchResponse):
            assert hasattr(results, "results")
            for r in results.results:
                assert r.title or r.url or r.snippet
        else:
            for r in results:
                assert isinstance(r, dict)
                assert "title" in r
                assert "url" in r or "snippet" in r

    def test_dedup(self):
        from search.engine import SearchEngine
        s = SearchEngine()
        results = s.search("test", max_results=5)
        if hasattr(results, "results"):
            urls = [r.url for r in results.results if r.url]
        else:
            urls = [r.get("url", "") for r in results if r.get("url")]
        assert len(urls) == len(set(urls)), "Duplicate URLs found"

    def test_add_remove_provider(self):
        from search.engine import search_engine
        orig = list(search_engine.providers)
        search_engine.add_provider("google")
        assert "google" in search_engine.providers
        search_engine.remove_provider("google")
        assert "google" not in search_engine.providers
        # Restore
        search_engine.providers = orig

    def test_add_invalid_provider(self):
        from search.engine import search_engine
        orig = list(search_engine.providers)
        search_engine.add_provider("nonexistent")
        assert search_engine.providers == orig  # unchanged

    def test_set_providers(self):
        from search.engine import search_engine
        orig = list(search_engine.providers)
        search_engine.set_providers(["duckduckgo", "google"])
        assert "duckduckgo" in search_engine.providers
        search_engine.providers = orig  # restore


# ═══════════════════════════════════════════════════════════════════
# VISION
# ═══════════════════════════════════════════════════════════════════
class TestVisionAnalyzer:
    @pytest.fixture
    def test_image(self):
        """Create a small test PNG image."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        img = Image.new("RGBA", (400, 300), (255, 0, 0, 255))
        img.save(path)
        yield path
        os.unlink(path)

    @pytest.fixture
    def test_jpg(self, test_image):
        """Convert test PNG to JPG for format conversion tests."""
        out = test_image.replace(".png", "_conv.jpg")
        img = Image.open(test_image)
        img = img.convert("RGB")
        img.save(out, "JPEG", quality=85)
        yield out
        if os.path.exists(out):
            os.unlink(out)

    def test_import(self):
        from vision.analyzer import vision, VisionAnalyzer
        assert vision is not None
        assert isinstance(vision, VisionAnalyzer)

    def test_methods_exist(self):
        from vision.analyzer import vision
        expected = [
            "analyze", "analyze_detailed", "ocr",
            "resize", "convert_format", "thumbnail", "get_image_info",
        ]
        for m in expected:
            assert hasattr(vision, m), f"Missing method: {m}"

    def test_analyze(self, test_image):
        from vision.analyzer import vision
        result = vision.analyze(test_image)
        assert "400x300" in result
        assert "PNG" in result

    def test_analyze_detailed(self, test_image):
        from vision.analyzer import vision
        info = vision.analyze_detailed(test_image)
        assert isinstance(info, dict)
        assert info["width"] == 400
        assert info["height"] == 300
        assert info["format"] == "PNG"

    def test_resize(self, test_image):
        from vision.analyzer import vision
        result = vision.resize(test_image, width=200)
        assert "200x150" in result or "yeniden" in result.lower()
        # Cleanup generated file
        for f in Path("/tmp").glob("test_vision_*"):
            f.unlink(missing_ok=True)

    def test_thumbnail(self, test_image):
        from vision.analyzer import vision
        result = vision.thumbnail(test_image, (100, 100))
        assert "100x" in result or "thumb" in result.lower()
        for f in Path("/tmp").glob("test_vision_*"):
            f.unlink(missing_ok=True)

    def test_convert_format(self, test_image):
        from vision.analyzer import vision
        out = test_image.replace(".png", "_converted.webp")
        result = vision.convert_format(test_image, target_format="webp", output_path=out)
        assert "WEBP" in result or "webp" in result.lower()
        assert os.path.exists(out)
        os.unlink(out)

    def test_convert_format_invalid(self, test_image):
        from vision.analyzer import vision
        result = vision.convert_format(test_image, target_format="invalid")
        assert "Gecersiz" in result

    def test_get_image_info(self, test_image):
        from vision.analyzer import vision
        info = vision.get_image_info(test_image)
        assert info is not None
        assert info["width"] == 400
        assert info["format"] == "PNG"

    def test_get_image_info_missing_file(self):
        from vision.analyzer import vision
        info = vision.get_image_info("/nonexistent/path.png")
        assert info is None

    def test_resize_with_height(self, test_image):
        from vision.analyzer import vision
        result = vision.resize(test_image, width=200, height=150)
        assert "200x150" in result
        for f in Path("/tmp").glob("test_vision_*"):
            f.unlink(missing_ok=True)

    def test_resize_no_aspect(self, test_image):
        from vision.analyzer import vision
        result = vision.resize(test_image, width=200, height=100, keep_aspect=False)
        assert "200x100" in result
        for f in Path("/tmp").glob("test_vision_*"):
            f.unlink(missing_ok=True)
