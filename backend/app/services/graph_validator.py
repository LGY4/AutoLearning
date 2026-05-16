from __future__ import annotations
"""GraphValidator — validates knowledge graph integrity.

Checks:
  1. Unique node IDs
  2. Edge references exist (source/target must be valid node IDs)
  3. Dependency existence (depends_on entries must be valid node IDs)
  4. Cycle detection (no circular prerequisites)
  5. Orphan detection (nodes with no edges)
  6. Topological sort validity
  7. Schema compliance (required fields, types)
  8. Source info presence (nodes should have source_refs)
"""

from typing import Dict,  List,  Optional

from collections import defaultdict

from app.schemas.graph import GraphData, ValidationResult


def validate_graph(graph: GraphData) -> ValidationResult:
    """Run all validation checks on a GraphData instance."""
    errors: List[str] = []
    warnings: List[str] = []

    nodes = graph.nodes
    edges = graph.edges

    node_ids = [n.id for n in nodes]
    node_id_set = set(node_ids)

    # 1. Unique node IDs
    seen_ids: set[str] = set()
    for nid in node_ids:
        if nid in seen_ids:
            errors.append(f"Duplicate node ID: '{nid}'")
        seen_ids.add(nid)

    # 2. Edge references exist
    for i, edge in enumerate(edges):
        if edge.source not in node_id_set:
            errors.append(f"Edge[{i}] source '{edge.source}' not found in nodes")
        if edge.target not in node_id_set:
            errors.append(f"Edge[{i}] target '{edge.target}' not found in nodes")

    # 3. Dependency existence
    for node in nodes:
        for dep in node.depends_on:
            if dep not in node_id_set:
                errors.append(f"Node '{node.id}' depends_on '{dep}' which does not exist")

    # 4. Cycle detection (DFS on depends_on)
    if _has_cycle(nodes):
        errors.append("Graph contains circular dependencies")

    # 5. Orphan detection
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge.source)
        connected.add(edge.target)
    for node in nodes:
        if node.id not in connected and not node.depends_on:
            warnings.append(f"Orphan node: '{node.id}' ({node.name}) — no edges or dependencies")

    # 6. Topological sort validity
    topo_order = _topological_sort_ids(nodes)
    if topo_order is None and not _has_cycle(nodes):
        warnings.append("Topological sort produced no result (empty graph?)")

    # 7. Schema compliance
    for node in nodes:
        if not node.id:
            errors.append(f"Node missing 'id' field")
        if not node.name:
            errors.append(f"Node '{node.id}' missing 'name' field")
        if node.level < 1:
            warnings.append(f"Node '{node.id}' has level < 1")

    # 8. Source info
    nodes_without_source = [n.id for n in nodes if not n.source_refs]
    if nodes_without_source:
        warnings.append(f"{len(nodes_without_source)} nodes have no source_refs: {', '.join(nodes_without_source[:5])}")

    # Stats
    stats = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "orphan_count": len([n for n in nodes if n.id not in connected and not n.depends_on]),
        "max_level": max((n.level for n in nodes), default=0),
        "avg_deps": round(sum(len(n.depends_on) for n in nodes) / max(len(nodes), 1), 1),
    }

    return ValidationResult(
        valid=len(errors) == 0,
        errors=errors,
        warnings=warnings,
        stats=stats,
    )


def _has_cycle(nodes) -> bool:
    """Detect cycles using DFS coloring."""
    adj: Dict[str, List[str]] = {n.id: list(n.depends_on) for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color: Dict[str, int] = {n.id: WHITE for n in nodes}

    def dfs(nid: str) -> bool:
        color[nid] = GRAY
        for dep in adj.get(nid, []):
            if dep not in color:
                continue
            if color[dep] == GRAY:
                return True
            if color[dep] == WHITE and dfs(dep):
                return True
        color[nid] = BLACK
        return False

    return any(dfs(nid) for nid, c in color.items() if c == WHITE)


def _topological_sort_ids(nodes) -> Optional[List[str]]:
    """Return node IDs in topological order, or None if cycle exists."""
    adj: Dict[str, List[str]] = {}
    in_degree: Dict[str, int] = {n.id: 0 for n in nodes}
    for n in nodes:
        adj.setdefault(n.id, [])
        for dep in n.depends_on:
            if dep in in_degree:
                adj.setdefault(dep, []).append(n.id)
                in_degree[n.id] += 1

    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    result: List[str] = []
    while queue:
        nid = queue.pop(0)
        result.append(nid)
        for child in adj.get(nid, []):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(result) != len(nodes):
        return None  # cycle
    return result
