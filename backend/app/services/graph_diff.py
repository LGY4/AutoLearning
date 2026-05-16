from __future__ import annotations
"""GraphDiff — compare two GraphData instances and produce a structured diff.

Detects:
  - Added / removed / changed nodes
  - Added / removed edges
  - Dependency changes (depends_on diffs)
  - Learning path changes
  - Metadata changes (version, status, confidence)
"""

from app.schemas.graph import GraphData


def diff_graphs(old: GraphData, new: GraphData) -> dict:
    """Compare two graphs and return a structured diff report."""
    old_nodes = {n.id: n for n in old.nodes}
    new_nodes = {n.id: n for n in new.nodes}

    old_ids = set(old_nodes.keys())
    new_ids = set(new_nodes.keys())

    added_ids = new_ids - old_ids
    removed_ids = old_ids - new_ids
    common_ids = old_ids & new_ids

    # Added nodes
    added_nodes = [
        {"id": nid, "name": new_nodes[nid].name, "level": new_nodes[nid].level}
        for nid in sorted(added_ids)
    ]

    # Removed nodes
    removed_nodes = [
        {"id": nid, "name": old_nodes[nid].name, "level": old_nodes[nid].level}
        for nid in sorted(removed_ids)
    ]

    # Changed nodes (name, level, description, depends_on, chunk_ids)
    changed_nodes = []
    for nid in sorted(common_ids):
        old_n = old_nodes[nid]
        new_n = new_nodes[nid]
        changes = {}
        if old_n.name != new_n.name:
            changes["name"] = {"old": old_n.name, "new": new_n.name}
        if old_n.level != new_n.level:
            changes["level"] = {"old": old_n.level, "new": new_n.level}
        if old_n.description != new_n.description:
            changes["description"] = {"old": old_n.description[:80], "new": new_n.description[:80]}
        if set(old_n.depends_on) != set(new_n.depends_on):
            changes["depends_on"] = {"old": sorted(old_n.depends_on), "new": sorted(new_n.depends_on)}
        if set(old_n.chunk_ids) != set(new_n.chunk_ids):
            changes["chunk_ids"] = {"old": sorted(old_n.chunk_ids), "new": sorted(new_n.chunk_ids)}
        if changes:
            changed_nodes.append({"id": nid, "changes": changes})

    # Edge diffs
    old_edges = {(e.source, e.target) for e in old.edges}
    new_edges = {(e.source, e.target) for e in new.edges}
    added_edges = [{"source": s, "target": t} for s, t in sorted(new_edges - old_edges)]
    removed_edges = [{"source": s, "target": t} for s, t in sorted(old_edges - new_edges)]

    # Learning path diffs
    old_paths = old.learning_paths or {}
    new_paths = new.learning_paths or {}
    path_changes = {}
    all_levels = set(list(old_paths.keys()) + list(new_paths.keys()))
    for level in sorted(all_levels):
        old_p = old_paths.get(level, [])
        new_p = new_paths.get(level, [])
        if old_p != new_p:
            path_changes[level] = {"old": old_p, "new": new_p}

    # Metadata diff
    meta_changes = {}
    if old.metadata.version != new.metadata.version:
        meta_changes["version"] = {"old": old.metadata.version, "new": new.metadata.version}
    if old.metadata.confidence != new.metadata.confidence:
        meta_changes["confidence"] = {"old": old.metadata.confidence, "new": new.metadata.confidence}
    if old.metadata.review_status != new.metadata.review_status:
        meta_changes["review_status"] = {"old": old.metadata.review_status.value, "new": new.metadata.review_status.value}

    # Summary
    total_changes = len(added_nodes) + len(removed_nodes) + len(changed_nodes) + len(added_edges) + len(removed_edges)

    return {
        "summary": {
            "total_changes": total_changes,
            "nodes_added": len(added_nodes),
            "nodes_removed": len(removed_nodes),
            "nodes_changed": len(changed_nodes),
            "edges_added": len(added_edges),
            "edges_removed": len(removed_edges),
            "paths_changed": len(path_changes),
            "old_version": old.metadata.version,
            "new_version": new.metadata.version,
        },
        "nodes": {
            "added": added_nodes,
            "removed": removed_nodes,
            "changed": changed_nodes,
        },
        "edges": {
            "added": added_edges,
            "removed": removed_edges,
        },
        "learning_paths": path_changes,
        "metadata": meta_changes,
    }
