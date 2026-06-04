"""Unified completion tracking: syncs learning path nodes and knowledge map."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.services import graph_service
from app.services.profile_event_service import ProfileEventType, emit_event
from app.services.profile_eval_service import evaluate_knowledge_point
from app.services.profile_service import get_profile


def mark_knowledge_point_completed(
    user_id: UUID,
    knowledge_point: str,
    source: str = "map",
    quiz_accuracy: float = 0.8,
) -> dict:
    """Mark a knowledge point as completed from any source.

    1. Update profile via profile event (feeds known_topics)
    2. If a learning path exists and has a matching node, mark it COMPLETED and unlock next

    Returns {"profile_updated": bool, "path_updated": bool, "path": ...}
    """
    result = {"profile_updated": False, "path_updated": False, "path": None}

    # 1. Update profile dimension
    profile = get_profile(user_id)
    if profile:
        dim = evaluate_knowledge_point(profile, knowledge_point, quiz_accuracy=quiz_accuracy, total_questions=1)
        emit_event(
            user_id,
            ProfileEventType.PATH_NODE_COMPLETE,
            {"knowledge_point": knowledge_point, "dimension": dim.model_dump()},
            confidence=0.6,
        )
        result["profile_updated"] = True

    # 2. Sync learning path node if exists
    path = repository.get_path(user_id)
    if path:
        target_node = None
        for node in path.nodes:
            if node.knowledge_point == knowledge_point and node.status.value != "completed":
                target_node = node
                break
        if target_node:
            updated_path = repository.complete_path_node(user_id, target_node.node_id)
            if updated_path:
                result["path_updated"] = True
                result["path"] = updated_path.model_dump(mode="json")

    return result
