from __future__ import annotations
"""Shared post-learning-update logic for both chat and start-stream paths.

Consolidates: profile update, strategy calculation, resource recommendation.
"""

from typing import List,  Optional

from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.profile import StudentProfile
from app.schemas.resource import LearningResource
from app.services import profile_eval_service, strategy_engine


def post_learning_update(
    user_id: UUID,
    knowledge_point: str,
    quiz_result: Optional[dict] = None,
    conversation_context: str = "",
    existing_resources: Optional[List[LearningResource]] = None,
    conversation_id: Optional[UUID] = None,
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
    else:
        resource_params = {"resource_types": ["document", "quiz"], "difficulty": "easy", "emphasis": "concept"}
        teaching_params = {"difficulty": "easy", "tutor_style": "supportive"}

    # 3. Resource recommendation (deduplicate against existing)
    existing_types = set()
    if existing_resources:
        existing_types = {r.resource_type for r in existing_resources}
        if hasattr(existing_resources[0], "resource_type") and hasattr(existing_resources[0].resource_type, "value"):
            existing_types = {r.resource_type.value for r in existing_resources}

    recommended = [t for t in resource_params.get("resource_types", []) if t not in existing_types]

    return {
        "updated_profile": profile,
        "resource_params": resource_params,
        "teaching_params": teaching_params,
        "recommended_types": recommended,
    }
