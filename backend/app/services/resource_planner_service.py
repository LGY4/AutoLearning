from __future__ import annotations
"""Resource Planner Service — strategic resource generation planning.

Analyzes user profile, weak topics, learning goals, and existing resources
to determine what should be generated next. Replaces the ad-hoc logic in
_auto_generate_for_weak_topics with a unified planning approach.
"""

import logging
from typing import List, Optional
from uuid import UUID

from app.schemas.profile import StudentProfile
from app.services import strategy_engine

logger = logging.getLogger(__name__)


def plan_resources_for_user(user_id: UUID) -> List[dict]:
    """Comprehensive resource planning: weak topics + goal + path recommendations.

    Returns list of planned items: [{knowledge_point, resource_type, difficulty, priority, source}]
    """
    from app.services.profile_service import get_profile
    from app.repositories.vertical_loop_repository import repository

    profile = get_profile(user_id)
    if not profile:
        return []

    # Gather existing resources for dedup
    existing = _get_existing_resource_keys(user_id)

    planned = []

    # 1. Weak topics (highest priority)
    planned.extend(plan_resources_for_weak_topics(user_id, profile))

    # 2. Learning goal resources
    goal = getattr(profile.learning_goal, "current_goal", None)
    if goal:
        subject = getattr(profile.basic_info, "major", None) or "计算机科学"
        goal_planned = plan_resources_for_goal(user_id, goal, subject)
        planned.extend(goal_planned)

    # 3. Path node recommendations
    try:
        path = repository.get_path(user_id)
        if path:
            for node in path.nodes:
                kp = node.knowledge_point
                for rt in (node.recommended_resource_types or []):
                    rt_str = rt.value if hasattr(rt, "value") else str(rt)
                    if (kp, rt_str) not in existing:
                        planned.append({
                            "knowledge_point": kp,
                            "resource_type": rt_str,
                            "difficulty": "medium",
                            "priority": 40,
                            "source": "path_node",
                        })
    except Exception:
        pass

    # Deduplicate and sort by priority
    planned = _deduplicate_planned(planned, existing)
    planned.sort(key=lambda x: x.get("priority", 0), reverse=True)

    return planned


def plan_resources_for_weak_topics(
    user_id: UUID,
    profile: StudentProfile,
) -> List[dict]:
    """Plan resources for weak topics based on strategy engine recommendations."""
    weak_topics = profile.knowledge_profile.weak_topics or []
    if not weak_topics:
        return []

    style = profile.learning_preference.learning_style
    existing = _get_existing_resource_keys(user_id)
    planned = []

    for kp in weak_topics[:3]:
        dim = profile.knowledge_profile.topic_dimensions.get(kp)
        if not dim:
            continue
        params = strategy_engine.get_resource_params(dim, style)
        recommended_types = params.get("resource_types", [])
        difficulty = params.get("difficulty", 1)
        diff_str = {1: "easy", 2: "medium", 3: "hard"}.get(difficulty, "medium")

        count = 0
        for rt in recommended_types:
            if (kp, rt) not in existing:
                planned.append({
                    "knowledge_point": kp,
                    "resource_type": rt,
                    "difficulty": diff_str,
                    "priority": 80,  # Weak topics = high priority
                    "source": "weak_topic",
                })
                count += 1
                if count >= 2:  # Up to 2 resource types per weak topic per cycle
                    break

    return planned


def plan_resources_for_goal(
    user_id: UUID,
    goal: str,
    subject: str,
) -> List[dict]:
    """Plan resources for a learning goal: path node types + goal-related topics."""
    from app.repositories.vertical_loop_repository import repository

    existing = _get_existing_resource_keys(user_id)
    planned = []

    # Get path nodes for the goal
    try:
        path = repository.get_path(user_id)
        if path and path.nodes:
            # Pick the first non-completed node's recommended types
            for node in path.nodes:
                if node.status.value in ("available", "learning"):
                    for rt in (node.recommended_resource_types or []):
                        rt_str = rt.value if hasattr(rt, "value") else str(rt)
                        if (node.knowledge_point, rt_str) not in existing:
                            planned.append({
                                "knowledge_point": node.knowledge_point,
                                "resource_type": rt_str,
                                "difficulty": "medium",
                                "priority": 60,
                                "source": "goal_path",
                            })
                    break  # Focus on current node
    except Exception:
        pass

    # If no path, generate basic resources for the goal topic (all types)
    if not planned:
        basic_types = ["document", "quiz", "mindmap", "flowchart", "code_case", "video", "animation", "reading"]
        for rt in basic_types:
            if (goal, rt) not in existing:
                planned.append({
                    "knowledge_point": goal,
                    "resource_type": rt,
                    "difficulty": "easy",
                    "priority": 50,
                    "source": "goal_basic",
                })

    return planned


def _get_existing_resource_keys(user_id: UUID) -> set:
    """Get set of (knowledge_point, resource_type) for existing resources."""
    from app.repositories.vertical_loop_repository import repository
    existing = set()
    try:
        for r in repository.list_user_resources(user_id):
            kp = r.get("knowledge_point", "")
            rt = r.get("resource_type", "")
            if kp and rt:
                existing.add((kp, rt))
    except Exception:
        pass
    return existing


def _deduplicate_planned(planned: List[dict], existing: set) -> List[dict]:
    """Remove duplicates: same (kp, resource_type) already exists or already planned."""
    seen = set()
    result = []
    for item in planned:
        key = (item["knowledge_point"], item["resource_type"])
        if key not in existing and key not in seen:
            seen.add(key)
            result.append(item)
    return result
