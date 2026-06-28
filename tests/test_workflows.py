"""Workflow engine tests — DAG node execution, conditions, loops."""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


class TestWorkflowNodes:
    def test_import_nodes(self):
        """All node types should be importable."""
        from workflows.nodes import LLMNode, ToolNode, ConditionNode, LoopNode
        assert LLMNode is not None
        assert ToolNode is not None
        assert ConditionNode is not None
        assert LoopNode is not None

    def test_llm_node(self):
        """LLMNode should accept node_id + optional config."""
        from workflows.nodes import LLMNode
        node = LLMNode(node_id="llm1", config={"prompt": "hello", "model": "default"})
        assert node.node_id == "llm1"

    def test_tool_node(self):
        """ToolNode should accept node_id + optional config."""
        from workflows.nodes import ToolNode
        node = ToolNode(node_id="t1", config={"tool": "read_file", "params": {}})
        assert node.node_id == "t1"

    def test_condition_node(self):
        """ConditionNode should accept node_id."""
        from workflows.nodes import ConditionNode
        node = ConditionNode(node_id="c1", config={"condition": "result == 'ok'"})
        assert node.node_id == "c1"

    def test_loop_node(self):
        """LoopNode should accept node_id + max_iter config."""
        from workflows.nodes import LoopNode
        node = LoopNode(node_id="l1", config={"max_iterations": 5})
        assert node.node_id == "l1"

    def test_graph_nodes(self):
        """Graph should support add_node and edges."""
        from workflows.graph import WorkflowGraph
        g = WorkflowGraph()
        g.add_node("llm", "llm")
        g.add_node("tool", "tool")
        assert "llm" in g.nodes
        assert "tool" in g.nodes

    def test_graph_edges(self):
        """Graph should store edges between nodes."""
        from workflows.graph import WorkflowGraph
        g = WorkflowGraph()
        g.add_node("a", "llm")
        g.add_node("b", "tool")
        g.add_edge("a", "b")
        assert g.edges is not None

    def test_engine_import(self):
        """Engine should import cleanly."""
        from workflows.engine import WorkflowEngine
        assert WorkflowEngine is not None
