"""Read the compiled Tesserae knowledge graph (``<root>/.tesserae/graph.json``) and
serve it as a browsable graph: node search, a focused N-hop subgraph around a node,
node detail, and a non-empty landing overview.

The CLI has no graph-structure command, but the compiler writes the full
``{nodes:[{id,name,type,aliases,description,source_path}], edges:[{source,target,
type,evidence}]}`` to ``graph.json``. We load it once per file mtime (it's ~14 MB /
7k nodes) into an id→node map + adjacency, so search/subgraph are in-memory fast.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

# path -> {mtime, nodes: {id: node}, adj: {id: [(nbr_id, edge, direction)]}, edges: [...]}
_cache: dict[str, dict] = {}
_lock = threading.Lock()


def graph_path(root: str) -> str:
    return os.path.join(root, ".tesserae", "graph.json")


def _load(root: str) -> Optional[dict]:
    path = graph_path(root)
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _lock:
        cached = _cache.get(path)
        if cached and cached["mtime"] == mtime:
            return cached
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        logger.warning("memory_graph: failed to read %s", path, exc_info=True)
        return None
    nodes = {n["id"]: n for n in data.get("nodes", []) if n.get("id")}
    adj: dict[str, list] = {}
    edges = []
    for e in data.get("edges", []):
        s, t = e.get("source"), e.get("target")
        if s in nodes and t in nodes:
            adj.setdefault(s, []).append((t, e, "out"))
            adj.setdefault(t, []).append((s, e, "in"))
            edges.append(e)
    entry = {"mtime": mtime, "nodes": nodes, "adj": adj, "edges": edges}
    with _lock:
        _cache[path] = entry
    return entry


def _degree(g: dict, nid: str) -> int:
    return len(g["adj"].get(nid, []))


def _node_summary(g: dict, node: dict, *, center: bool = False) -> dict:
    return {
        "id": node["id"],
        "name": node.get("name") or node["id"],
        "type": node.get("type") or "Node",
        "degree": _degree(g, node["id"]),
        "center": center,
    }


def _edge_out(e: dict) -> dict:
    return {
        "source": e.get("source"),
        "target": e.get("target"),
        "type": e.get("type") or "related",
        "evidence": (e.get("evidence") or "")[:220] or None,
    }


def available(root: str) -> bool:
    return os.path.exists(graph_path(root))


def search_nodes(root: str, q: str, *, limit: int = 25) -> list[dict]:
    g = _load(root)
    ql = (q or "").lower().strip()
    if not g or not ql:
        return []
    scored: list[tuple[int, dict]] = []
    for node in g["nodes"].values():
        name = (node.get("name") or "").lower()
        aliases = " ".join(node.get("aliases") or []).lower()
        desc = (node.get("description") or "").lower()
        if ql == name:
            base = 100
        elif name.startswith(ql):
            base = 75
        elif ql in name:
            base = 60
        elif ql in aliases:
            base = 40
        elif ql in desc:
            base = 20
        else:
            continue
        # tie-break toward well-connected nodes
        scored.append((base + min(_degree(g, node["id"]), 20), node))
    scored.sort(key=lambda x: -x[0])
    return [_node_summary(g, n) for _, n in scored[:limit]]


def subgraph(root: str, node_id: str, *, hops: int = 1, max_nodes: int = 60) -> dict:
    g = _load(root)
    if not g or node_id not in g["nodes"]:
        return {"nodes": [], "edges": [], "center": node_id, "truncated": False}
    seen = {node_id}
    frontier = [node_id]
    truncated = False
    for _ in range(max(1, hops)):
        nxt = []
        for nid in frontier:
            for nbr, _edge, _dir in g["adj"].get(nid, []):
                if nbr in seen:
                    continue
                if len(seen) >= max_nodes:
                    truncated = True
                    break
                seen.add(nbr)
                nxt.append(nbr)
            if truncated:
                break
        frontier = nxt
        if truncated or not frontier:
            break
    node_list = [_node_summary(g, g["nodes"][i], center=(i == node_id)) for i in seen]
    edge_seen: set = set()
    edge_list = []
    for e in g["edges"]:
        s, t = e.get("source"), e.get("target")
        if s in seen and t in seen:
            key = (s, t, e.get("type"))
            if key not in edge_seen:
                edge_seen.add(key)
                edge_list.append(_edge_out(e))
    return {"nodes": node_list, "edges": edge_list, "center": node_id, "truncated": truncated}


def node_detail(root: str, node_id: str) -> Optional[dict]:
    g = _load(root)
    node = g["nodes"].get(node_id) if g else None
    if not node:
        return None
    neighbors = []
    for nbr, edge, direction in g["adj"].get(node_id, [])[:50]:
        nb = g["nodes"].get(nbr)
        if nb:
            neighbors.append(
                {
                    "id": nbr,
                    "name": nb.get("name") or nbr,
                    "type": nb.get("type") or "Node",
                    "edge_type": edge.get("type") or "related",
                    "direction": direction,
                }
            )
    return {
        **_node_summary(g, node),
        "description": node.get("description"),
        "aliases": node.get("aliases") or [],
        "source_path": node.get("source_path"),
        "neighbors": neighbors,
    }


def overview(root: str, *, max_nodes: int = 50) -> dict:
    """A connected landing subgraph around the most-connected node, so the page is
    never empty — plus the graph's total node/edge counts."""
    g = _load(root)
    if not g or not g["nodes"]:
        return {"nodes": [], "edges": [], "total_nodes": 0, "total_edges": 0, "seed": None}
    seed = max(g["nodes"], key=lambda i: _degree(g, i))
    sg = subgraph(root, seed, hops=2, max_nodes=max_nodes)
    sg["total_nodes"] = len(g["nodes"])
    sg["total_edges"] = len(g["edges"])
    sg["seed"] = seed
    return sg
