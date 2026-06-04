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
    dimension_results: Optional[dict] = None,
) -> KnowledgeDimension:
    """Evaluate four dimensions for a knowledge point after learning.

    - Has dimension_results → per-dimension evaluation (preferred)
    - Has quiz_accuracy → overall accuracy fallback
    - No quiz data → return existing dimension

    Returns raw new_dim WITHOUT merging — caller is responsible for merge.
    """
    existing_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)

    if dimension_results and any(v.get("total", 0) > 0 for v in dimension_results.values()):
        # Per-dimension evaluation (each dimension tested independently)
        def _dim_level(correct: int, total: int) -> str:
            if total == 0:
                return "low"
            acc = correct / total
            if acc >= 0.8:
                return "high"
            elif acc >= 0.5:
                return "mid"
            return "low"

        return KnowledgeDimension(
            mastery=_dim_level(dimension_results.get("mastery", {}).get("correct", 0), dimension_results.get("mastery", {}).get("total", 0)),
            application=_dim_level(dimension_results.get("application", {}).get("correct", 0), dimension_results.get("application", {}).get("total", 0)),
            memory=_dim_level(dimension_results.get("memory", {}).get("correct", 0), dimension_results.get("memory", {}).get("total", 0)),
            understanding=_dim_level(dimension_results.get("understanding", {}).get("correct", 0), dimension_results.get("understanding", {}).get("total", 0)),
        )

    if quiz_accuracy is not None and total_questions >= 1:
        # Require >= 3 questions for "high" classification to avoid cold-start inflation
        can_be_high = total_questions >= 3

        # Mastery: knows the concept
        if quiz_accuracy >= 0.8 and can_be_high:
            mastery = "high"
        elif quiz_accuracy >= 0.5:
            mastery = "mid"
        else:
            mastery = "low"

        # Application: can use in practice
        if quiz_accuracy >= 0.8 and can_be_high:
            application = "high"
        elif quiz_accuracy >= 0.5:
            application = "mid"
        else:
            application = "low"

        # Memory: retains knowledge (scales slower — needs repeated success)
        if quiz_accuracy >= 0.9 and total_questions >= 3:
            memory = "high"
        elif quiz_accuracy >= 0.6:
            memory = "mid"
        else:
            memory = "low"

        # Understanding: grasps the why
        if quiz_accuracy >= 0.8 and can_be_high:
            understanding = "high"
        elif quiz_accuracy >= 0.5:
            understanding = "mid"
        else:
            understanding = "low"

        return KnowledgeDimension(
            mastery=mastery,
            application=application,
            memory=memory,
            understanding=understanding,
        )

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

    saved = False
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
            saved = True
            break
        except Exception as exc:
            if "Version conflict" in str(exc) and attempt < max_retries - 1:
                logger.warning("Profile version conflict, retrying (%d/%d)", attempt + 1, max_retries)
                continue
            raise

    if not saved:
        logger.error("Failed to save profile after %d retries for user %s, kp %s", max_retries, user_id, knowledge_point)
        return None

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
