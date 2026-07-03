"""Graphify tools — knowledge graph querying.

Reads from graphify-out/graph.json. The build pipeline is a separate script,
not exposed as a tool to the agent. Only query tools are here.
"""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool

GRAPH_PATH = Path("graphify-out/graph.json")


def _load_graph():
    """Load graph.json, gracefully fail if not found."""
    if not GRAPH_PATH.exists():
        return None
    try:
        from networkx.readwrite import json_graph
        data = json.loads(GRAPH_PATH.read_text())
        return json_graph.node_link_graph(data, edges="links")
    except (json.JSONDecodeError, OSError, KeyError, ImportError):
        return None


def _graph_required():
    """Check graph — called at the start of every tool."""
    if not GRAPH_PATH.exists():
        return "Graph not built yet. Run `graphify .` in terminal."
    G = _load_graph()
    if G is None:
        return "Graph file is corrupted. Rebuild with `graphify .` in terminal."
    return G


def _find_node_by_label(G, term: str):
    """Find the node with the best matching label."""
    t = term.lower()
    scored = sorted(
        [(sum(1 for w in t.split() if w in G.nodes[n].get("label", "").lower()), n)
         for n in G.nodes()],
        reverse=True,
    )
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _set_graph_flag():
    """graphify_query succeeded — notify executor, block batch_python."""
    try:
        from tools.executor import executor
        executor._graph_data_available = True
    except ImportError:
        pass


@register_tool(
    name="graphify",
    description=(
        "Knowledge graph query tool. 4 modes:\n"
        "- query: Learn all connections with ONE CLICK. Example: 'who uses the event bus?' or 'What is ToolRegistry?'\n"
        "- path: Find shortest connection chain between two concepts. Example: 'main.py' to 'Logger'\n"
        "- nodes: List most critical modules, the most connected nodes in the project.\n"
        "- stats: Get overall graph statistics.\n"
        "Don't bother with read_file, search_files, grep, batch_python — the graph already has all import/call/reference relationships."
    ),
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["query", "path", "nodes", "stats"],
                "description": "Action: query=search, path=find path, nodes=most critical nodes, stats=statistics",
            },
            "question": {
                "type": "string",
                "description": "(query) Natural language question or concept name. Example: 'who uses the event bus' or 'ToolRegistry'",
            },
            "source": {
                "type": "string",
                "description": "(path) Starting concept. Example: 'Config', 'main.py'",
            },
            "target": {
                "type": "string",
                "description": "(path) Target concept. Example: 'Database', 'Logger'",
            },
            "limit": {
                "type": "integer",
                "default": 10,
                "description": "(nodes) How many nodes to show (max 30)",
            },
            "mode": {
                "type": "string",
                "enum": ["bfs", "dfs"],
                "default": "bfs",
                "description": "(query) bfs=wide coverage, dfs=deep chain",
            },
            "depth": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 6,
                "description": "(query) How many steps to traverse (1-6)",
            },
        },
        "required": ["action"],
    },
    toolset="graphify",
)
def graphify_tool(action: str, question: str = "", source: str = "", target: str = "",
                  limit: int = 10, mode: str = "bfs", depth: int = 3) -> str:
    """Merged graphify tool — dispatches by action parameter."""
    # ── action="query" ───────────────────────────────────────────
    if action == "query":
        G = _graph_required()
        if isinstance(G, str):
            return json.dumps({"error": G})

        if not question or not question.strip():
            return json.dumps({
                "error": "What do you want to learn? Example questions:",
                "examples": [
                    "'which modules connect to the event bus'",
                    "'what is ToolRegistry'",
                    "'path between main.py and Logger'",
                ],
            })

        # Graphify success — notify executor, block batch_python
        _set_graph_flag()

        # Short query (1-3 words) → single node detail (explain mode)
        words = question.strip().split()
        if len(words) <= 4:
            nid = _find_node_by_label(G, question)
            if nid:
                data_n = G.nodes[nid]
                connections = []
                for neighbor in G.neighbors(nid):
                    edge = G.edges[nid, neighbor]
                    connections.append({
                        "relation": edge.get("relation", ""),
                        "target": G.nodes[neighbor].get("label", neighbor),
                        "confidence": edge.get("confidence", ""),
                        "source_file": G.nodes[neighbor].get("source_file", ""),
                    })
                return json.dumps({
                    "concept": data_n.get("label", nid),
                    "id": nid,
                    "source_file": data_n.get("source_file", ""),
                    "source_location": data_n.get("source_location", ""),
                    "file_type": data_n.get("file_type", ""),
                    "degree": G.degree(nid),
                    "connections": connections,
                    "connection_count": len(connections),
                }, ensure_ascii=False)

        # Long query → BFS/DFS traversal
        terms = [t.lower() for t in words if len(t) > 3]

        # Find best-matching nodes
        scored = []
        for nid, ndata in G.nodes(data=True):
            label = ndata.get("label", "").lower()
            score = sum(1 for t in terms if t in label)
            if score > 0:
                scored.append((score, nid))
        scored.sort(reverse=True)
        start_nodes = [nid for _, nid in scored[:5]]

        if not start_nodes:
            return json.dumps({"error": f"No nodes match '{question}'.", "nodes": [], "edges": []})

        subgraph_nodes = set()
        subgraph_edges = []

        if mode == "dfs":
            visited = set()
            stack = [(n, 0) for n in reversed(start_nodes)]
            while stack:
                node, d = stack.pop()
                if node in visited or d > depth:
                    continue
                visited.add(node)
                subgraph_nodes.add(node)
                for neighbor in G.neighbors(node):
                    if neighbor not in visited:
                        stack.append((neighbor, d + 1))
                        subgraph_edges.append((node, neighbor))
        else:
            frontier = set(start_nodes)
            subgraph_nodes = set(start_nodes)
            for _ in range(depth):
                next_frontier = set()
                for n in frontier:
                    for neighbor in G.neighbors(n):
                        if neighbor not in subgraph_nodes:
                            next_frontier.add(neighbor)
                            subgraph_edges.append((n, neighbor))
                subgraph_nodes.update(next_frontier)
                frontier = next_frontier

        def relevance(nid):
            label = G.nodes[nid].get("label", "").lower()
            return sum(1 for t in terms if t in label)

        ranked = sorted(subgraph_nodes, key=relevance, reverse=True)

        nodes_out = []
        for nid in ranked:
            d = G.nodes[nid]
            nodes_out.append({
                "id": nid,
                "label": d.get("label", nid),
                "source_file": d.get("source_file", ""),
                "file_type": d.get("file_type", ""),
            })

        edges_out = []
        for u, v in subgraph_edges:
            if u in subgraph_nodes and v in subgraph_nodes:
                d = G.edges[u, v]
                edges_out.append({
                    "source": G.nodes[u].get("label", u),
                    "target": G.nodes[v].get("label", v),
                    "relation": d.get("relation", ""),
                    "confidence": d.get("confidence", ""),
                })

        return json.dumps({
            "query": question,
            "mode": mode,
            "start_nodes": [G.nodes[n].get("label", n) for n in start_nodes],
            "node_count": len(nodes_out),
            "edge_count": len(edges_out),
            "nodes": nodes_out,
            "edges": edges_out,
        }, ensure_ascii=False)

    # ── action="path" ────────────────────────────────────────────
    if action == "path":
        G = _graph_required()
        if isinstance(G, str):
            return json.dumps({"error": G})

        src = _find_node_by_label(G, source)
        tgt = _find_node_by_label(G, target)

        if not src:
            return json.dumps({"error": f"'{source}' not found."})
        if not tgt:
            return json.dumps({"error": f"'{target}' not found."})

        import networkx as nx
        try:
            path = nx.shortest_path(G, src, tgt)
        except nx.NetworkXNoPath:
            return json.dumps({"error": f"No path between '{source}' and '{target}'."})

        steps = []
        for i, nid in enumerate(path):
            label = G.nodes[nid].get("label", nid)
            if i < len(path) - 1:
                edge = G.edges[nid, path[i + 1]]
                steps.append({
                    "node": label,
                    "relation": edge.get("relation", ""),
                    "confidence": edge.get("confidence", ""),
                })
            else:
                steps.append({"node": label})

        return json.dumps({
            "source": source,
            "target": target,
            "hops": len(path) - 1,
            "path": steps,
        }, ensure_ascii=False)

    # ── action="nodes" ───────────────────────────────────────────
    if action == "nodes":
        G = _graph_required()
        if isinstance(G, str):
            return json.dumps({"error": G})

        limit = min(limit, 30)
        sorted_nodes = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:limit]

        nodes = []
        for nid, degree in sorted_nodes:
            d = G.nodes[nid]
            nodes.append({
                "label": d.get("label", nid),
                "degree": degree,
                "source_file": d.get("source_file", ""),
                "file_type": d.get("file_type", ""),
            })

        return json.dumps({
            "total_nodes": G.number_of_nodes(),
            "total_edges": G.number_of_edges(),
            "god_nodes": nodes,
        }, ensure_ascii=False)

    # ── action="stats" ───────────────────────────────────────────
    if action == "stats":
        G = _graph_required()
        if isinstance(G, str):
            return json.dumps({"error": G})

        try:
            from graphify.cluster import cluster as _cluster_fn
            communities = _cluster_fn(G)
            community_count = len(communities)
        except (ImportError, ValueError, KeyError, TypeError):
            community_count = 0

        conf_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0}
        for _, _, d in G.edges(data=True):
            c = d.get("confidence", "")
            if c in conf_counts:
                conf_counts[c] += 1

        type_counts: dict[str, int] = {}
        for _, d in G.nodes(data=True):
            ft = d.get("file_type", "unknown")
            type_counts[ft] = type_counts.get(ft, 0) + 1

        return json.dumps({
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
            "community_count": community_count,
            "density": round(2 * G.number_of_edges() / max(G.number_of_nodes() * (G.number_of_nodes() - 1), 1), 6),
            "confidence_breakdown": conf_counts,
            "file_type_breakdown": type_counts,
        }, ensure_ascii=False)

    return json.dumps({"error": f"Unknown action: '{action}'. Must be one of: query, path, nodes, stats"})


# ── Backward-compatible aliases ─────────────────
graphify_query_tool = lambda question="", mode="bfs", depth=3: graphify_tool("query", question=question, mode=mode, depth=depth)
graphify_path_tool = lambda source, target: graphify_tool("path", source=source, target=target)
graphify_god_nodes_tool = lambda limit=10: graphify_tool("nodes", limit=limit)
graphify_stats_tool = lambda: graphify_tool("stats")
