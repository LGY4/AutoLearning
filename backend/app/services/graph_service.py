from __future__ import annotations
"""Knowledge graph service — loads graph, resolves prerequisites and learning paths.

Graph source priority: DB-published graph (via graph_repository) > static JSON file.
"""

from typing import Dict,  List,  Optional

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_SUBJECT = "数据结构"


def _graph_file() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "knowledge_graph.json"


def _normalize_edge(e: dict) -> dict:
    """Normalize edge to use 'from'/'to' keys (supports both from/to and source/target)."""
    return {
        "from": e.get("from") or e.get("source", ""),
        "to": e.get("to") or e.get("target", ""),
        "type": e.get("type", "prerequisite"),
    }


def _load_static_graph() -> dict:
    """Load graph from the static JSON file (fallback)."""
    path = _graph_file()
    if not path.exists():
        logger.error("知识图谱文件缺失: %s — 路径规划将无前置依赖", path)
        return {"nodes": [], "edges": [], "learning_paths": {}}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if "edges" in raw:
        raw["edges"] = [_normalize_edge(e) for e in raw["edges"]]
    return raw


def _graphdata_to_dict(graph_data) -> dict:
    """Convert a GraphData schema object to the dict format used by this service."""
    d = graph_data.model_dump(mode="json")
    nodes = d.get("nodes", [])
    edges = [_normalize_edge(e) for e in d.get("edges", [])]
    return {
        "course": d.get("metadata", {}).get("course_name", ""),
        "nodes": nodes,
        "edges": edges,
        "learning_paths": d.get("learning_paths", {}),
    }


# Cache: subject -> graph dict
_graph_cache: Dict[str, dict] = {}


def load_graph(subject: Optional[str] = None) -> dict:
    """Load knowledge graph for a subject.

    Priority: DB-published graph > static JSON file.
    Results are cached in memory; call invalidate_cache() to refresh.
    """
    subj = subject or _DEFAULT_SUBJECT

    if subj in _graph_cache:
        return _graph_cache[subj]

    # Try DB-published graph first
    try:
        from app.repositories.graph_repository import graph_repository
        db_graph = graph_repository.get_published_graph(subj)
        if db_graph:
            result = _graphdata_to_dict(db_graph)
            if result.get("nodes"):
                _graph_cache[subj] = result
                logger.info("Loaded graph for '%s' from DB (%d nodes)", subj, len(result["nodes"]))
                return result
    except Exception:
        logger.debug("DB graph lookup failed for '%s', falling back to static", subj)

    # Fallback to static JSON (only cache under default subject to avoid wrong-key pollution)
    static = _load_static_graph()
    if subj == _DEFAULT_SUBJECT:
        _graph_cache[subj] = static
    return static


def invalidate_cache(subject: Optional[str] = None) -> None:
    """Clear cached graph data. Call after graph publish/update."""
    if subject:
        _graph_cache.pop(subject, None)
    else:
        _graph_cache.clear()


def get_node(node_id: str, subject: Optional[str] = None) -> Optional[dict]:
    for node in load_graph(subject).get("nodes", []):
        if node["id"] == node_id:
            return node
    return None


def get_prerequisites(node_id: str, subject: Optional[str] = None) -> List[dict]:
    """Return prerequisite nodes for a given node."""
    node = get_node(node_id, subject)
    if not node:
        return []
    prereq_ids = node.get("depends_on", [])
    return [n for n in load_graph(subject).get("nodes", []) if n["id"] in prereq_ids]


def get_next_nodes(node_id: str, subject: Optional[str] = None) -> List[dict]:
    """Return nodes that depend on the given node."""
    graph = load_graph(subject)
    next_ids = [e["to"] for e in graph.get("edges", []) if e["from"] == node_id]
    return [n for n in graph.get("nodes", []) if n["id"] in next_ids]


def get_learning_path(level: str, subject: Optional[str] = None) -> List[dict]:
    """Return ordered nodes for a learning path level (beginner/intermediate/advanced)."""
    graph = load_graph(subject)
    path_ids = graph.get("learning_paths", {}).get(level, [])
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    return [nodes_by_id[pid] for pid in path_ids if pid in nodes_by_id]


def topological_sort(subject: Optional[str] = None) -> List[dict]:
    """Return all nodes in dependency order (topological sort)."""
    graph = load_graph(subject)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    in_degree = {n["id"]: 0 for n in nodes}
    adj: Dict[str, List[str]] = {n["id"]: [] for n in nodes}
    for e in edges:
        adj[e["from"]].append(e["to"])
        in_degree[e["to"]] = in_degree.get(e["to"], 0) + 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result_ids: List[str] = []
    while queue:
        nid = queue.pop(0)
        result_ids.append(nid)
        for child in adj.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    nodes_by_id = {n["id"]: n for n in nodes}
    return [nodes_by_id[nid] for nid in result_ids if nid in nodes_by_id]


def get_node_with_context(node_id: str, subject: Optional[str] = None) -> Optional[dict]:
    """Return a node enriched with prerequisites and next_nodes."""
    node = get_node(node_id, subject)
    if not node:
        return None
    return {
        **node,
        "prerequisites": [n["id"] for n in get_prerequisites(node_id, subject)],
        "next_nodes": [n["id"] for n in get_next_nodes(node_id, subject)],
    }


def get_full_graph(subject: Optional[str] = None) -> dict:
    """Return the full graph with enriched node data."""
    graph = load_graph(subject)
    enriched = []
    for node in graph.get("nodes", []):
        enriched.append({
            **node,
            "prerequisites": [e["from"] for e in graph.get("edges", []) if e["to"] == node["id"]],
            "next_nodes": [e["to"] for e in graph.get("edges", []) if e["from"] == node["id"]],
        })
    return {
        "course": graph.get("course", ""),
        "nodes": enriched,
        "edges": graph.get("edges", []),
        "learning_paths": graph.get("learning_paths", {}),
    }


def resolve_prerequisite_chain(node_ids: List[str], subject: Optional[str] = None) -> List[str]:
    """Given a set of desired node IDs, return them in dependency order,
    including any missing prerequisites inserted before their dependents."""
    graph = load_graph(subject)
    nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])

    # Build adjacency: parent -> children
    adj: Dict[str, List[str]] = {}
    for e in edges:
        adj.setdefault(e["from"], []).append(e["to"])

    needed: set[str] = set(node_ids)
    # BFS backwards to collect all transitive prerequisites
    queue = list(node_ids)
    while queue:
        nid = queue.pop(0)
        node = nodes_by_id.get(nid)
        if not node:
            continue
        for prereq_id in node.get("depends_on", []):
            if prereq_id not in needed:
                needed.add(prereq_id)
                queue.append(prereq_id)

    # Topological sort over the needed set
    in_degree = {nid: 0 for nid in needed}
    sub_adj: Dict[str, List[str]] = {nid: [] for nid in needed}
    for e in edges:
        if e["from"] in needed and e["to"] in needed:
            sub_adj[e["from"]].append(e["to"])
            in_degree[e["to"]] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result: List[str] = []
    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for child in sub_adj.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    return result
