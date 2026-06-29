#!/usr/bin/env python3
"""Graphify build pipeline — AST extraction + graph build + cluster + export.

Kullanim:
    python scripts/graphify_build.py <path>
    python scripts/graphify_build.py <path> --update
    python scripts/graphify_build.py <path> --deep   # (sadece AST, semantic ayri)

Bu script sadece AST extraction yapar (ucretsiz). Semantic extraction
(subagent + LLM) gerekiyorsa kullaniciyi yonlendirir.

Agent tool olarak gormez — sadece terminal'dan calistirilir.
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Graphify build pipeline")
    parser.add_argument("path", nargs="?", default=".", help="Taranacak dizin")
    parser.add_argument("--update", action="store_true", help="Incremental re-extraction")
    parser.add_argument("--deep", action="store_true", help="Sadece AST (semantic ayrica)")
    args = parser.parse_args()

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"HATA: Dizin bulunamadi: {target}")
        sys.exit(1)

    print(f"Graphify build basliyor: {target}")
    t0 = time.time()

    # Step 1: Detect
    print("[1/5] Dosyalar taranıyor...")
    from graphify.detect import detect
    detection = detect(target)
    total = detection.get("total_files", 0)
    words = detection.get("total_words", 0)
    print(f"  -> {total} dosya, ~{words:,} kelime")

    if total == 0:
        print("HATA: Desteklenen dosya bulunamadi.")
        sys.exit(1)

    if words > 2_000_000 or total > 200:
        from collections import Counter
        counts: Counter = Counter()
        for cat, flist in detection["files"].items():
            for f in flist:
                p = Path(f)
                try:
                    parts = p.relative_to(target).parts
                    if parts:
                        counts[parts[0]] += 1
                except ValueError:
                    continue
        print(f"  UYARI: Buyuk corpus ({total} dosya). Top 5 alt dizin:")
        for name, cnt in counts.most_common(5):
            print(f"    {name}/: {cnt} dosya")

    # Step 2: AST extraction (code files only)
    ast_nodes = 0
    ast_edges = 0
    code_files = [f for f in detection["files"].get("code", [])]
    if code_files:
        print(f"[2/5] AST extraction ({len(code_files)} kod dosyasi)...")
        from graphify.extract import collect_files, extract
        files = []
        for f in code_files:
            p = Path(f)
            if p.is_dir():
                files.extend(collect_files(p))
            else:
                files.append(p)
        if files:
            result = extract(files)
            ast_nodes = len(result["nodes"])
            ast_edges = len(result["edges"])
            Path(".graphify_ast.json").write_text(json.dumps(result, indent=2))
            print(f"  -> {ast_nodes} node, {ast_edges} edge")
        else:
            Path(".graphify_ast.json").write_text(json.dumps({"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}))
            print("  -> AST icin kod dosyasi bulunamadi")
    else:
        Path(".graphify_ast.json").write_text(json.dumps({"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}))
        print("[2/5] Kod dosyasi yok — AST atlandi")

    # Step 3: Semantic check
    has_noncode = bool(
        detection["files"].get("document", []) or
        detection["files"].get("paper", []) or
        detection["files"].get("image", [])
    )
    if has_noncode:
        print("[3/5] Semantic extraction gerekiyor (doc/paper/image dosyalari var)")
        print("  -> LLM tabanli semantic extraction icin su komutu calistir:")
        print(f"  /graphify {target} {'--update ' if args.update else ''}")
        print("  -> Bu script sadece AST ile graph olusturacak.")
    else:
        print("[3/5] Sadece kod dosyasi — semantic gerekmez, devam")

    # Step 4: Build graph + cluster + analyze
    print("[4/5] Graph olusturuluyor...")
    ast = json.loads(Path(".graphify_ast.json").read_text())

    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_json

    G = build_from_json(ast)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    questions = suggest_questions(G, communities, labels)
    tokens = {"input": ast.get("input_tokens", 0), "output": ast.get("output_tokens", 0)}

    out_dir = Path("graphify-out")
    out_dir.mkdir(exist_ok=True)

    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, str(target), suggested_questions=questions)
    (out_dir / "GRAPH_REPORT.md").write_text(report)
    to_json(G, communities, str(out_dir / "graph.json"))
    print(f"  -> {G.number_of_nodes()} node, {G.number_of_edges()} edge, {len(communities)} community")

    # Step 5: Export
    print("[5/5] Cikti dosyalari yaziliyor...")
    from graphify.export import to_obsidian, to_canvas, to_html

    n = to_obsidian(G, communities, str(out_dir / "obsidian"), community_labels=labels or None, cohesion=cohesion)
    print(f"  -> Obsidian vault: {n} notes -> {out_dir / 'obsidian'}/")

    to_canvas(G, communities, str(out_dir / "obsidian/graph.canvas"), community_labels=labels or None)
    print(f"  -> Canvas: {out_dir / 'obsidian' / 'graph.canvas'}")

    if G.number_of_nodes() <= 5000:
        to_html(G, communities, str(out_dir / "graph.html"), community_labels=labels or None)
        print(f"  -> HTML: {out_dir / 'graph.html'}")
    else:
        print(f"  -> HTML atlandi ({G.number_of_nodes()} node > 5000 limiti)")

    elapsed = time.time() - t0
    print(f"\nBitti. {elapsed:.1f}s")
    print(f"Ciktilar: {out_dir.resolve()}/")
    print(f"  graphify-out/GRAPH_REPORT.md")
    print(f"  graphify-out/graph.json")
    print(f"  graphify-out/obsidian/  (Obsidian vault)")

    # Cleanup
    for f in [".graphify_ast.json"]:
        Path(f).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
