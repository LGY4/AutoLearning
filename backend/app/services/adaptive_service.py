from __future__ import annotations
"""Shared post-learning-update logic for both chat and start-stream paths.

Consolidates: profile update, strategy calculation, resource recommendation.
"""

import logging
import threading
from typing import List, Optional

_DIFF_MAP = {1: "easy", 2: "medium", 3: "hard"}

from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.profile import StudentProfile
from app.schemas.resource import LearningResource
from app.services import profile_eval_service, strategy_engine

logger = logging.getLogger(__name__)


def post_learning_update(
    user_id: UUID,
    knowledge_point: str,
    quiz_result: Optional[dict] = None,
    conversation_context: str = "",
    existing_resources: Optional[List[LearningResource]] = None,
    conversation_id: Optional[UUID] = None,
    dimension_results: Optional[dict] = None,
) -> dict:
    """Shared post-learning-update: profile update + strategy + resource recommendation.

    Args:
        user_id: User ID
        knowledge_point: The knowledge point being learned
        quiz_result: Optional quiz result dict with 'accuracy' and 'total' keys
        conversation_context: Unused (kept for API compat, profile only updates from quiz data)
        existing_resources: Resources already generated (for dedup)

    Returns:
        dict with updated_profile, resource_params, teaching_params, recommended_types
    """
    from app.services import profile_service
    profile = profile_service.get_profile(user_id, conversation_id=conversation_id)

    # 1. Profile update (only if quiz data available)
    if profile and quiz_result:
        accuracy = quiz_result.get("accuracy")
        total = quiz_result.get("total", 0)
        if accuracy is not None and total >= 1:
            dim = profile_eval_service.evaluate_knowledge_point(
                profile, knowledge_point,
                quiz_accuracy=accuracy,
                total_questions=total,
                dimension_results=dimension_results,
            )
            from app.services.profile_event_service import ProfileEventType, emit_event
            emit_event(user_id, ProfileEventType.ADAPTIVE_QUIZ, {"knowledge_point": knowledge_point, "dimension": dim.model_dump(), "accuracy": accuracy, "total": total}, confidence=0.7)
            profile = profile_service.get_profile(user_id, conversation_id=conversation_id)

    # 2. Strategy calculation
    if not profile:
        profile = profile_service.get_profile(user_id, conversation_id=conversation_id)

    updated_dim = None
    if profile:
        updated_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)

    if updated_dim:
        style = profile.learning_preference.learning_style if profile else "mixed"
        resource_params = strategy_engine.get_resource_params(updated_dim, style)
        teaching_params = strategy_engine.get_teaching_params(updated_dim)
        # Normalize difficulty to string for downstream consumers
        if isinstance(resource_params.get("difficulty"), int):
            resource_params["difficulty"] = _DIFF_MAP.get(resource_params["difficulty"], "medium")
        if isinstance(teaching_params.get("difficulty"), int):
            teaching_params["difficulty"] = _DIFF_MAP.get(teaching_params["difficulty"], "medium")
    else:
        resource_params = {"resource_types": ["document", "quiz"], "difficulty": "easy", "emphasis": "concept"}
        teaching_params = {"difficulty": "easy", "tutor_style": "supportive"}

    # 3. Resource recommendation (deduplicate against existing)
    existing_types = set()
    if existing_resources:
        def _rt_val(r):
            rt = r.resource_type
            return rt.value if hasattr(rt, "value") else str(rt)
        existing_types = {_rt_val(r) for r in existing_resources}

    recommended = [t for t in resource_params.get("resource_types", []) if t not in existing_types]

    # 4. Invalidate cached recommendations so they reflect updated profile
    if updated_dim:
        try:
            from app.services.recommendation_service import invalidate_recommendations
            invalidate_recommendations(user_id)
        except Exception:
            pass  # non-blocking

    # 5. Strategic resource planning and auto-generation (background)
    if profile:
        try:
            _strategic_auto_generate(user_id, profile)
        except Exception:
            logger.warning("Strategic auto-generation failed", exc_info=True)

    # 6. Auto-generate learning path if user has goal but no active path (synchronous)
    path_generated = False
    if profile:
        try:
            path_generated = _auto_generate_learning_path(user_id, profile)
        except Exception:
            logger.warning("Auto-generation of learning path failed", exc_info=True)

    # 7. If path was just generated, trigger goal-based resource generation
    if path_generated:
        try:
            goal = getattr(profile.learning_goal, "current_goal", None)
            if goal:
                subject = getattr(profile.basic_info, "major", None) or "计算机科学"
                _generate_goal_resources(user_id, goal, subject)
        except Exception:
            logger.warning("Goal-based resource generation failed", exc_info=True)

    # 8. Consume pending suggested_generation recommendations
    suggestions_consumed = 0
    try:
        suggestions_consumed = _consume_suggested_generations(user_id)
    except Exception:
        logger.warning("Consuming suggested generations failed", exc_info=True)

    # Build changes dict for frontend to react to
    changes = {}
    if path_generated:
        changes["path_generated"] = True
    if suggestions_consumed > 0:
        changes["suggestions_consumed"] = suggestions_consumed

    return {
        "updated_profile": profile,
        "resource_params": resource_params,
        "teaching_params": teaching_params,
        "recommended_types": recommended,
        "changes": changes,
    }


def _strategic_auto_generate(user_id: UUID, profile: StudentProfile) -> None:
    """Strategic auto-generation: plan and generate resources based on profile + goals + path.

    Replaces _auto_generate_for_weak_topics with a unified planning approach.
    Runs in background thread to avoid blocking.
    """
    try:
        from app.services.resource_planner_service import plan_resources_for_user
        planned = plan_resources_for_user(user_id)
    except Exception:
        logger.debug("Resource planning failed, falling back to weak topics only")
        planned = []

    if not planned:
        return

    def _generate():
        for item in planned[:3]:  # Max 3 per update cycle
            _generate_single_resource(user_id, item)

    threading.Thread(target=_generate, daemon=True).start()


def _generate_single_resource(user_id: UUID, item: dict) -> bool:
    """Generate a single resource from a planned item.

    Args:
        item: {knowledge_point, resource_type, difficulty, priority, source}

    Returns True if generation succeeded.
    """
    from app.core.enums import ResourceType

    kp = item.get("knowledge_point", "")
    rtype = item.get("resource_type", "document")
    difficulty = item.get("difficulty", "medium")

    if not kp:
        return False

    try:
        resource_type = ResourceType(rtype)
    except ValueError:
        resource_type = ResourceType.DOCUMENT

    try:
        repository.create_resource(
            user_id=user_id,
            knowledge_point=kp,
            resource_type=resource_type,
            difficulty=difficulty,
        )
        logger.info("Auto-generated %s for %s (source: %s)", rtype, kp, item.get("source", "unknown"))

        # Refresh recommendations after generation
        try:
            from app.services.recommendation_service import invalidate_recommendations
            invalidate_recommendations(user_id)
        except Exception:
            pass

        return True
    except Exception:
        logger.warning("Failed to auto-generate %s for %s", rtype, kp, exc_info=True)
        return False


def _generate_goal_resources(user_id: UUID, goal: str, subject: str) -> None:
    """Generate resources for a learning goal after path creation."""
    try:
        from app.services.resource_planner_service import plan_resources_for_goal
        planned = plan_resources_for_goal(user_id, goal, subject)
    except Exception:
        return

    if not planned:
        return

    def _generate():
        for item in planned[:5]:  # More items allowed for goal-based generation
            _generate_single_resource(user_id, item)

    threading.Thread(target=_generate, daemon=True).start()


def _auto_generate_learning_path(user_id: UUID, profile: StudentProfile) -> bool:
    """Auto-generate a learning path if user has a goal but no active path.

    Returns True if a new path was created.
    """
    goal = getattr(profile.learning_goal, "current_goal", None)
    if not goal:
        return False

    existing_path = repository.get_path(user_id)
    if existing_path and existing_path.status in ("active", "paused"):
        return False  # already has an active path

    subject = getattr(profile.basic_info, "major", None) or "计算机科学"

    try:
        repository.create_path(user_id, goal, subject)
        logger.info("Auto-generated learning path for user %s, goal: %s", user_id, goal)
        return True
    except Exception:
        logger.warning("Failed to auto-generate learning path for user %s", user_id, exc_info=True)
        return False


def _consume_suggested_generations(user_id: UUID) -> int:
    """Consume pending suggested_generation recommendations by triggering resource creation.

    Returns number of suggestions consumed.
    """
    try:
        recs = repository.get_pending_suggestions(user_id)
    except Exception:
        return 0

    if not recs:
        return 0

    consumed = 0
    # Limit to 2 per update cycle to avoid overload
    for rec in recs[:2]:
        try:
            repository.consume_suggested_generation(user_id, rec)
            consumed += 1
            logger.info("Consumed suggested_generation: %s", rec.get("knowledge_point", ""))
        except Exception:
            logger.warning("Failed to consume suggestion", exc_info=True)
    return consumed
