"""Graphify tools — knowledge graph sorgulama.

graphify-out/graph.json dosyasindan okur. Build pipeline'i ayri bir script'tir,
tool olarak agent'a acik degildir. Sadece sorgulama tool'lari burada.
"""
from __future__ import annotations
import json
from pathlib import Path

from tools.registry import register_tool

GRAPH_PATH = Path("graphify-out/graph.json")


def _load_graph():
    """graph.json'u yukle, yoksa graceful fail."""
    if not GRAPH_PATH.exists():
        return None
    try:
        from networkx.readwrite import json_graph
        data = json.loads(GRAPH_PATH.read_text())
        return json_graph.node_link_graph(data, edges="links")
    except Exception:
        return None


def _graph_required():
    """Graph kontrolu — her tool'un basinda cagrilir."""
    if not GRAPH_PATH.exists():
        return "Graph henuz olusturulmamis. Terminal'de `graphify .` calistir."
    G = _load_graph()
    if G is None:
        return "Graph dosyasi bozuk. Terminal'de `graphify .` ile yeniden olustur."
    return G


def _find_node_by_label(G, term: str):
    """Label'de en iyi eslesen node'u bul."""
    t = term.lower()
    scored = sorted(
        [(sum(1 for w in t.split() if w in G.nodes[n].get("label", "").lower()), n)
         for n in G.nodes()],
        reverse=True,
    )
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _set_graph_flag():
    """graphify_query basarili oldu — executor'a bildir, batch_python bloklansin."""
    try:
        from tools.executor import executor
        executor._graph_data_available = True
    except Exception:
        pass


@register_tool(
    name="graphify_query",
    description=(
        "TEK TIKLA tum baglantilari ogren. Ornek: 'event bus kim tarafindan kullaniliyor?' veya 'ToolRegistry nedir?' "
        "Eger soru tek bir konsept adiysa (ornek: 'EventBus', 'ToolRegistry') o node'un detayini gosterir. "
        "Eger baglanti sorusuysa tum agi BFS/DFS ile tarar. "
        "read_file, search_files, grep, batch_python ile ugrasma — graph'ta zaten butun import/call/reference iliskileri var."
    ),
    parameters={
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "Dogal dil sorusu veya konsept adi. Ornek: 'event bus kim tarafindan kullaniliyor' veya 'ToolRegistry'",
            },
            "mode": {
                "type": "string",
                "enum": ["bfs", "dfs"],
                "default": "bfs",
                "description": "bfs=genis cevre, dfs=derin zincir",
            },
            "depth": {
                "type": "integer",
                "default": 3,
                "minimum": 1,
                "maximum": 6,
                "description": "Kac adim oteye git (1-6)",
            },
        },
        "required": [],
    },
    toolset="graphify",
)
def graphify_query_tool(question: str = "", mode: str = "bfs", depth: int = 3) -> str:
    """Grafikte sorgu yap. Bos soru = yardim mesaji."""
    G = _graph_required()
    if isinstance(G, str):
        return json.dumps({"error": G})

    if not question or not question.strip():
        return json.dumps({
            "error": "Ne ogrenmek istiyorsun? Ornek sorular:",
            "examples": [
                "'event bus ile hangi moduller baglantili'",
                "'ToolRegistry nedir'",
                "'main.py ile Logger arasindaki yol'",
            ],
        })

    # Graphify basarili oldu — executor'a bildir, batch_python bloklansin
    _set_graph_flag()

    # Kisa sorgu (1-3 kelime) → tek node detayi goster (explain mode)
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

    # Uzun sorgu → BFS/DFS traversal
    terms = [t.lower() for t in words if len(t) > 3]

    # En iyi eslesen node'lari bul
    scored = []
    for nid, ndata in G.nodes(data=True):
        label = ndata.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:5]]

    if not start_nodes:
        return json.dumps({"error": f"'{question}' ile eslesen node bulunamadi.", "nodes": [], "edges": []})

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


@register_tool(
    name="graphify_path",
    description=(
        "Iki konsept arasindaki en kisa baglanti zincirini bulur. "
        "Ornek: 'main.py' ile 'Logger' arasinda hangi moduller var? "
        "read_file + grep ile ugrasip 15 tool call harcama, tek cagrida yolu gosterir."
    ),
    parameters={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Baslangic konsepti. Ornek: 'Config', 'main.py'",
            },
            "target": {
                "type": "string",
                "description": "Hedef konsept. Ornek: 'Database', 'Logger'",
            },
        },
        "required": ["source", "target"],
    },
    toolset="graphify",
)
def graphify_path_tool(source: str, target: str) -> str:
    """Iki node arasi en kisa yol."""
    G = _graph_required()
    if isinstance(G, str):
        return json.dumps({"error": G})

    src = _find_node_by_label(G, source)
    tgt = _find_node_by_label(G, target)

    if not src:
        return json.dumps({"error": f"'{source}' bulunamadi."})
    if not tgt:
        return json.dumps({"error": f"'{target}' bulunamadi."})

    import networkx as nx
    try:
        path = nx.shortest_path(G, src, tgt)
    except nx.NetworkXNoPath:
        return json.dumps({"error": f"'{source}' ile '{target}' arasinda yol bulunamadi."})

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


@register_tool(
    name="graphify_god_nodes",
    description=(
        "Projedeki en kritik modulleri, en cok baglantili node'lari tek cagrida listeler. "
        "Kod tabanina yeni girdiginde 'nereden baslamaliyim?' sorusunun cevabi. "
        "Hic dosya okumadan projenin mimarisini anlamak icin kullan."
    ),
    parameters={
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "default": 10,
                "description": "Kac node gosterilsin (max 30)",
            },
        },
        "required": [],
    },
    toolset="graphify",
)
def graphify_god_nodes_tool(limit: int = 10) -> str:
    """En cok baglantili node'lari getir."""
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


@register_tool(
    name="graphify_stats",
    description=(
        "Graph'in genel istatistiklerini getirir: kac node, kac edge, kac community, "
        "confidence dagilimi. Projenin graph'a ne kadar aktarildigini gormek icin kullan."
    ),
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    toolset="graphify",
)
def graphify_stats_tool() -> str:
    """Graph istatistiklerini getir."""
    G = _graph_required()
    if isinstance(G, str):
        return json.dumps({"error": G})

    try:
        from graphify.cluster import cluster as _cluster_fn
        communities = _cluster_fn(G)
        community_count = len(communities)
    except Exception:
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
