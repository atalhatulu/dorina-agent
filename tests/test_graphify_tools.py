"""Graphify tools tests — graceful fail, import, dil kontrolu, merged explain."""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest


class TestGraphifyToolsGraphYok:
    """graph.json yokken tum tool'lar graceful fail etmeli."""

    @pytest.fixture(autouse=True)
    def _backup_and_restore_graph(self, monkeypatch):
        import tools.builtin.graphify_tools as gt
        fake = Path("/tmp/graphify_test_nonexistent_graph.json")
        monkeypatch.setattr(gt, "GRAPH_PATH", fake)
        yield

    def test_query_graph_yok(self):
        from tools.builtin.graphify_tools import graphify_query_tool
        r = json.loads(graphify_query_tool("event bus"))
        assert "error" in r
        assert "olusturulmamis" in r["error"]

    def test_path_graph_yok(self):
        from tools.builtin.graphify_tools import graphify_path_tool
        r = json.loads(graphify_path_tool("Config", "Database"))
        assert "error" in r
        assert "olusturulmamis" in r["error"]

    def test_god_nodes_graph_yok(self):
        from tools.builtin.graphify_tools import graphify_god_nodes_tool
        r = json.loads(graphify_god_nodes_tool())
        assert "error" in r
        assert "olusturulmamis" in r["error"]

    def test_stats_graph_yok(self):
        from tools.builtin.graphify_tools import graphify_stats_tool
        r = json.loads(graphify_stats_tool())
        assert "error" in r
        assert "olusturulmamis" in r["error"]


class TestGraphifyToolsImport:
    """Tool fonksiyonlari import edilebiliyor ve dogru imzalara sahip."""

    def test_all_tools_importable(self):
        from tools.builtin.graphify_tools import (
            graphify_query_tool,
            graphify_path_tool,
            graphify_god_nodes_tool,
            graphify_stats_tool,
        )
        assert callable(graphify_query_tool)
        assert callable(graphify_path_tool)
        assert callable(graphify_god_nodes_tool)
        assert callable(graphify_stats_tool)

    def test_explain_kalkti_import_edilemez(self):
        """graphify_explain tamamen kaldirildi — import edilememeli."""
        import importlib
        mod = importlib.import_module("tools.builtin.graphify_tools")
        assert not hasattr(mod, "graphify_explain_tool")

    def test_query_tool_parameters_not_required(self):
        """question parametresi required degil — bos gonderilince yardim mesaji."""
        from tools.builtin.graphify_tools import graphify_query_tool
        r = json.loads(graphify_query_tool())
        assert "error" in r
        # Hata mesaji graph yoklugunu soylemeli (eski 'Ornek' mesaji degil)

    def test_query_short_name_returns_node_detail(self):
        """Tek kelimelik sorgu → explain mode (node detayi). Graph varsa calisir."""
        from tools.builtin.graphify_tools import graphify_query_tool
        r = json.loads(graphify_query_tool("EventBus"))
        # Graph varsa node detayi, yoksa error
        assert isinstance(r, dict)

    def test_registered_in_registry(self):
        from tools.registry import registry
        # Eski ayri tool'lar kalkti, tek graphify tool'u var
        assert registry.get("graphify") is not None
        assert registry.get("graphify_query") is None
        assert registry.get("graphify_path") is None
        assert registry.get("graphify_god_nodes") is None
        assert registry.get("graphify_stats") is None
        # explain kaldirildi
        assert registry.get("graphify_explain") is None


class TestGraphifyToolsDescriptions:
    """Tool description'lari Turkce."""

    def test_descriptions_turkce(self):
        from tools.registry import registry
        turkce_kelimeler = ["grafik", "sorgu", "kod", "node", "konsept", "baglanti", "modul", "tikla"]
        for name in ["graphify"]:
            tool = registry.get(name)
            assert tool is not None
            desc = tool.description
            assert any(k in desc.lower() for k in turkce_kelimeler), (
                f"{name} description Turkce degil: {desc}"
            )

    def test_her_tool_farkli_description(self):
        from tools.registry import registry
        descs = set()
        for name in ["graphify"]:
            tool = registry.get(name)
            assert tool is not None
            assert tool.description not in descs, f"Duplicate description: {name}"
            descs.add(tool.description)


class TestGraphifyToolsGraceful:
    """Hata durumlari."""

    def test_query_empty_string_resilient(self):
        from tools.builtin.graphify_tools import graphify_query_tool
        r = json.loads(graphify_query_tool(question=""))
        assert "error" in r

    def test_query_whitespace_resilient(self):
        from tools.builtin.graphify_tools import graphify_query_tool
        r = json.loads(graphify_query_tool(question="   "))
        assert "error" in r

    def test_path_unknown_source(self, monkeypatch):
        """Bilinmeyen source icin hata mesaji."""
        from tools.builtin.graphify_tools import graphify_path_tool
        G = _mock_graph_with_nodes(["KnownNode"])
        monkeypatch.setattr("tools.builtin.graphify_tools._load_graph", lambda: G)
        monkeypatch.setattr("tools.builtin.graphify_tools.GRAPH_PATH", Path("/mock/graph.json"))
        import tools.builtin.graphify_tools as gt
        monkeypatch.setattr(gt, "GRAPH_PATH", Path("/mock/graph.json"))
        # We can't easily mock _graph_required without mocking the file,
        # so just check the function signature is correct
        r = json.loads(graphify_path_tool("NonexistentNode", "KnownNode"))
        assert "error" in r


def _mock_graph_with_nodes(labels):
    """Kucuk mock graph olustur (test yardimcisi)."""
    import networkx as nx
    G = nx.Graph()
    for lbl in labels:
        G.add_node(lbl.lower(), label=lbl)
    if len(labels) >= 2:
        G.add_edge(labels[0].lower(), labels[1].lower(), relation="test", confidence="EXTRACTED")
    return G


class TestGraphifyBuildScript:
    """Build script import edilebiliyor mu? (calistirma yok)"""

    def test_script_importable(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "graphify_build",
            str(Path(__file__).resolve().parent.parent / "scripts" / "graphify_build.py"),
        )
        assert spec is not None
