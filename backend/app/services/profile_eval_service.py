from __future__ import annotations
"""Profile evaluation — four-dimension assessment and update."""

from typing import Optional

import logging
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.profile import KnowledgeDimension, StudentProfile
from app.services import model_gateway, profile_service

logger = logging.getLogger(__name__)


def evaluate_knowledge_point(
    profile: StudentProfile,
    knowledge_point: str,
    quiz_accuracy: Optional[float] = None,
    total_questions: int = 0,
    conversation_context: str = "",
) -> KnowledgeDimension:
    """Evaluate four dimensions for a knowledge point after learning.

    - Has quiz data → rule-based evaluation
    - No quiz data → return existing dimension (no LLM inference from conversation)
    """
    from app.services.strategy_engine import merge_dimensions

    existing_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)

    if quiz_accuracy is not None and total_questions >= 1:
        # Confidence scales with number of questions answered
        confidence = min(0.6 + total_questions * 0.05, 0.95)

        if quiz_accuracy >= 0.8:
            mastery, memory = "high", "high"
        elif quiz_accuracy >= 0.5:
            mastery, memory = "mid", "mid"
        else:
            mastery, memory = "low", "low"

        if quiz_accuracy >= 0.7:
            application = "mid"
            understanding = "mid"
        elif quiz_accuracy >= 0.4:
            application = "low"
            understanding = "mid"
        else:
            application = "low"
            understanding = "low"

        new_dim = KnowledgeDimension(
            mastery=mastery,
            application=application,
            memory=memory,
            understanding=understanding,
        )
        return merge_dimensions(existing_dim, new_dim, confidence=confidence)

    # No quiz data → return existing dimension unchanged
    return existing_dim or KnowledgeDimension()


def update_profile_dimensions(
    user_id: UUID,
    knowledge_point: str,
    new_dim: KnowledgeDimension,
    emit=None,
    max_retries: int = 3,
    mode: str = "overwrite",
    conversation_id: Optional[UUID] = None,
) -> Optional[StudentProfile]:
    """Update four-dimension profile for a knowledge point. Optimistic lock retry.

    mode:
        "overwrite" — replace the KP's dimension (default, for known KPs)
        "additive" — only write if KP doesn't exist yet (for new KPs)
    """
    from app.services.strategy_engine import compute_known_topics, compute_mastery_level, compute_overall_level, compute_weak_topics

    for attempt in range(max_retries):
        profile = profile_service.get_profile(user_id, conversation_id=conversation_id)
        if profile is None:
            return None

        topic_dimensions = dict(profile.knowledge_profile.topic_dimensions)
        if mode == "additive" and knowledge_point in topic_dimensions:
            # KP already exists, skip overwrite
            return profile
        topic_dimensions[knowledge_point] = new_dim

        overall_level = compute_overall_level(topic_dimensions)
        weak_topics = compute_weak_topics(topic_dimensions)
        known_topics = compute_known_topics(topic_dimensions)
        mastery_level = compute_mastery_level(topic_dimensions)

        new_kp = profile.knowledge_profile.model_copy(update={
            "topic_dimensions": topic_dimensions,
            "overall_level": overall_level,
            "weak_topics": weak_topics,
            "known_topics": known_topics,
            "mastery_level": mastery_level,
        })
        new_dynamic = profile.dynamic_update.model_copy(update={
            "last_updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "update_source": "learning_loop",
            "update_reason": f"学习「{knowledge_point}」后四维度更新",
        })
        profile = profile.model_copy(update={
            "knowledge_profile": new_kp,
            "dynamic_update": new_dynamic,
            "version": profile.version + 1,
        })

        try:
            from app.repositories.vertical_loop_repository import repository
            if conversation_id:
                from app.services import conversation_service
                session = conversation_service.get_conversation(conversation_id)
                if session and session.profile_id:
                    repository.save_profile_in_place(session.profile_id, profile)
                else:
                    repository.save_profile(profile)
            else:
                repository.save_profile(profile)
            break
        except Exception as exc:
            if "Version conflict" in str(exc) and attempt < max_retries - 1:
                logger.warning("Profile version conflict, retrying (%d/%d)", attempt + 1, max_retries)
                continue
            raise

    if emit:
        emit({
            "agent_name": "profile_agent",
            "stage": "profile_update",
            "status": "done",
            "progress": 0,
            "hint": f"画像已更新：{knowledge_point} → {new_dim.archetype}",
            "data": {
                "knowledge_point": knowledge_point,
                "dimension": new_dim.model_dump(),
                "overall_level": overall_level,
            },
        })

    return profile
