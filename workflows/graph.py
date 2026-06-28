"""Workflow Graph Definition — DAG-based graph with nodes and edges.

Inspired by LangGraph's StateGraph pattern and CrewAI Flow.
"""

from __future__ import annotations
from typing import Any, Callable
from dataclasses import dataclass, field


@dataclass
class GraphNode:
    """A single node in the workflow graph."""
    id: str
    type: str  # "LLM", "Tool", "Code", "Condition", "Loop", "Input", "Output"
    config: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GraphEdge:
    """A directed edge between two nodes."""
    source: str      # Source node ID
    target: str      # Target node ID
    condition: str | None = None  # Optional condition label (for Condition nodes)


class WorkflowGraph:
    """DAG-based workflow graph.

    Usage:
        graph = WorkflowGraph()
        graph.add_node("start", "Input", {"description": "User input"})
        graph.add_node("llm1", "LLM", {"model": "deepseek", "prompt": "..."})
        graph.add_node("tool1", "Tool", {"tool": "web_search"})
        graph.add_edge("start", "llm1")
        graph.add_edge("llm1", "tool1")
        graph.add_edge("tool1", "llm1", condition="needs_more_info")
        graph.add_edge("tool1", "output", condition="done")
    """

    def __init__(self):
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []
        self._adjacency: dict[str, list[tuple[str, str | None]]] = {}  # node_id -> [(target, condition)]
        self._parent_map: dict[str, list[str]] = {}  # node_id -> [parents]

    def add_node(self, node_id: str, node_type: str, config: dict | None = None, metadata: dict | None = None) -> GraphNode:
        """Add a node to the graph."""
        node = GraphNode(
            id=node_id,
            type=node_type,
            config=config or {},
            metadata=metadata or {},
        )
        self.nodes[node_id] = node
        if node_id not in self._adjacency:
            self._adjacency[node_id] = []
        if node_id not in self._parent_map:
            self._parent_map[node_id] = []
        return node

    def add_edge(self, source: str, target: str, condition: str | None = None) -> GraphEdge:
        """Add a directed edge between two nodes."""
        if source not in self.nodes:
            raise ValueError(f"Source node '{source}' not found")
        if target not in self.nodes:
            raise ValueError(f"Target node '{target}' not found")
        edge = GraphEdge(source=source, target=target, condition=condition)
        self.edges.append(edge)
        self._adjacency.setdefault(source, []).append((target, condition))
        self._parent_map.setdefault(target, []).append(source)
        return edge

    def get_children(self, node_id: str) -> list[tuple[str, str | None]]:
        """Get all child nodes with their conditions."""
        return self._adjacency.get(node_id, [])

    def get_parents(self, node_id: str) -> list[str]:
        """Get all parent node IDs."""
        return self._parent_map.get(node_id, [])

    def get_entry_nodes(self) -> list[str]:
        """Get nodes with no parents (entry points)."""
        return [nid for nid in self.nodes if not self._parent_map.get(nid)]

    def get_exit_nodes(self) -> list[str]:
        """Get nodes with no children (exit points)."""
        return [nid for nid in self.nodes if not self._adjacency.get(nid)]

    def topological_sort(self) -> list[str]:
        """Topological sort using Kahn's algorithm."""
        in_degree = {nid: len(self._parent_map.get(nid, [])) for nid in self.nodes}
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        sorted_nodes = []

        # For condition edges, we need to handle them specially
        # Since conditions are branching, we sort by the primary path
        while queue:
            node_id = queue.pop(0)
            sorted_nodes.append(node_id)
            for child_id, _ in self._adjacency.get(node_id, []):
                in_degree[child_id] -= 1
                if in_degree[child_id] == 0:
                    queue.append(child_id)

        if len(sorted_nodes) != len(self.nodes):
            raise ValueError("Graph contains a cycle — cannot topologically sort")

        return sorted_nodes

    def validate(self) -> list[str]:
        """Validate the graph. Returns list of validation errors (empty if valid)."""
        errors = []
        if not self.nodes:
            errors.append("Graph has no nodes")
        if not self.get_entry_nodes():
            errors.append("Graph has no entry nodes (all nodes have parents)")
        if not self.get_exit_nodes():
            errors.append("Graph has no exit nodes (all nodes have children)")
        # Check for cycles
        try:
            self.topological_sort()
        except ValueError as e:
            errors.append(str(e))
        # Validate node IDs referenced in edges
        for edge in self.edges:
            if edge.source not in self.nodes:
                errors.append(f"Edge source '{edge.source}' not in nodes")
            if edge.target not in self.nodes:
                errors.append(f"Edge target '{edge.target}' not in nodes")
        return errors

    def to_dict(self) -> dict[str, Any]:
        """Export graph to dictionary (for serialization/checkpointing)."""
        return {
            "nodes": {nid: {"type": n.type, "config": n.config, "metadata": n.metadata}
                      for nid, n in self.nodes.items()},
            "edges": [{"source": e.source, "target": e.target, "condition": e.condition}
                      for e in self.edges],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowGraph:
        """Load graph from dictionary (restore from checkpoint)."""
        graph = cls()
        # Restore nodes preserving id order
        if "nodes" in data:
            for nid, ndata in data["nodes"].items():
                # Skip if node already exists
                if nid not in graph.nodes:
                    graph.add_node(nid, ndata.get("type", "LLM"), ndata.get("config"), ndata.get("metadata"))
        if "edges" in data:
            for edata in data["edges"]:
                graph.add_edge(edata["source"], edata["target"], edata.get("condition"))
        return graph
