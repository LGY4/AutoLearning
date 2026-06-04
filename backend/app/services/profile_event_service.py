"""Profile Event Service — event-driven profile update architecture.

All profile mutations go through emit_event → apply_pending_events → save_profile(master).
Events write directly to master profile. Snapshots are read-only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from uuid import UUID, uuid4

from app.schemas.profile import DynamicUpdate, KnowledgeDimension, StudentProfile

logger = logging.getLogger(__name__)


class ProfileEventType(str, Enum):
    DIAGNOSTIC_QUIZ = "diagnostic_quiz"
    ADAPTIVE_QUIZ = "adaptive_quiz"
    EXERCISE_GRADE = "exercise_grade"
    PATH_NODE_COMPLETE = "path_node_complete"
    WRONG_POINTS = "wrong_points"
    USER_EDIT = "user_edit"
    LLM_EXTRACT = "llm_extract"
    RESOURCE_CONSUMPTION = "resource_consumption"
    CONVERSATION_BEHAVIOR = "conversation_behavior"
    REVIEW_COMPLETE = "review_complete"


def emit_event(
    user_id: UUID,
    event_type: ProfileEventType | str,
    event_payload: dict,
    confidence: float,
    source_type: str = "agent",
    source_id: Optional[UUID] = None,
) -> UUID:
    """Emit a profile event and apply it synchronously.

    Returns the event ID. The event is persisted with status='pending',
    then apply_pending_events is called immediately.
    """
    from app.repositories.vertical_loop_repository import repository

    event_id = repository.emit_event(
        user_id=user_id,
        event_type=event_type if isinstance(event_type, str) else event_type.value,
        event_payload=event_payload,
        confidence=confidence,
        source_type=source_type,
        source_id=source_id,
    )
    apply_pending_events(user_id)
    return event_id


def apply_pending_events(user_id: UUID, max_events: int = 20) -> Optional[StudentProfile]:
    """Process pending events for a user in FIFO order.

    Reads pending events, applies each to the master profile,
    marks them 'applied' or 'failed', saves the final profile.
    """
    from app.repositories.vertical_loop_repository import repository

    events = repository.list_pending_events(user_id, limit=max_events)
    if not events:
        return repository.get_profile(user_id)

    profile = repository.get_profile(user_id)
    if not profile:
        # No master profile yet — DIAGNOSTIC_QUIZ and LLM_EXTRACT can create one
        _cold_start_types = {ProfileEventType.DIAGNOSTIC_QUIZ.value, ProfileEventType.LLM_EXTRACT.value}
        for ev in events:
            if ev["event_type"] in _cold_start_types:
                handler = _apply_diagnostic_quiz if ev["event_type"] == ProfileEventType.DIAGNOSTIC_QUIZ.value else _apply_llm_extract
                profile = handler(None, ev["event_payload"], ev["confidence"])
                profile = repository.save_profile_and_update_event(profile, ev["id"], "applied")
            else:
                repository.update_event_status(ev["id"], "skipped", "No master profile yet")
        return profile

    # Sync in-memory version with the DB's latest profile_version.
    # get_profile reads version from profile_json (typically 1 from snapshots),
    # but save_profile checks against the DB row's profile_version column.
    # Without this sync, any handler that does version+1 would mismatch.
    db_latest_version = repository.get_latest_profile_version(user_id)
    if db_latest_version is not None and profile.version != db_latest_version:
        profile = profile.model_copy(update={"version": db_latest_version})

    for ev in events:
        try:
            profile = _apply_event(profile, ev["event_type"], ev["event_payload"], ev["confidence"])
            profile = repository.save_profile_and_update_event(profile, ev["id"], "applied")
        except Exception as exc:
            logger.exception("Failed to apply profile event %s", ev["id"])
            repository.update_event_status(ev["id"], "failed", str(exc))

    return profile


def _apply_event(
    profile: StudentProfile,
    event_type: str,
    payload: dict,
    confidence: float,
) -> StudentProfile:
    """Dispatch to type-specific handler."""
    handlers = {
        ProfileEventType.DIAGNOSTIC_QUIZ.value: _apply_diagnostic_quiz,
        ProfileEventType.ADAPTIVE_QUIZ.value: _apply_adaptive_quiz,
        ProfileEventType.EXERCISE_GRADE.value: _apply_exercise_grade,
        ProfileEventType.PATH_NODE_COMPLETE.value: _apply_path_node_complete,
        ProfileEventType.WRONG_POINTS.value: _apply_wrong_points,
        ProfileEventType.USER_EDIT.value: _apply_user_edit,
        ProfileEventType.LLM_EXTRACT.value: _apply_llm_extract,
        ProfileEventType.RESOURCE_CONSUMPTION.value: _apply_resource_consumption,
        ProfileEventType.CONVERSATION_BEHAVIOR.value: _apply_conversation_behavior,
        ProfileEventType.REVIEW_COMPLETE.value: _apply_review_complete,
    }
    handler = handlers.get(event_type)
    if not handler:
        logger.warning("Unknown profile event type: %s", event_type)
        return profile
    return handler(profile, payload, confidence)


# ── Type-specific handlers ──────────────────────────────────────────────

def _apply_diagnostic_quiz(profile: Optional[StudentProfile], payload: dict, confidence: float) -> StudentProfile:
    """Cold-start: full profile creation from diagnostic quiz.

    When profile exists, merge knowledge and goal fields while preserving
    accumulated behavioral state (learning_behavior, resource_preference, etc.).
    """
    if profile is None:
        new_profile = StudentProfile.model_validate(payload)
        # Ensure version doesn't conflict with any existing DB row
        try:
            from app.repositories.vertical_loop_repository import repository
            db_version = repository.get_latest_profile_version(new_profile.user_id)
            if db_version is not None and db_version >= new_profile.version:
                new_profile = new_profile.model_copy(update={"version": db_version + 1})
        except Exception:
            pass
        return new_profile
    # If profile exists, merge knowledge/goal from diagnostic onto existing profile
    if confidence >= 0.8:
        new = StudentProfile.model_validate(payload)
        return profile.model_copy(update={
            "knowledge_profile": new.knowledge_profile,
            "learning_goal": new.learning_goal,
            "basic_info": new.basic_info,
            "completeness_score": max(profile.completeness_score, new.completeness_score),
            "confidence_score": max(profile.confidence_score, new.confidence_score * confidence),
            "dynamic_update": DynamicUpdate(
                last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                update_source="diagnostic_quiz",
                update_reason="diagnostic quiz merge",
            ),
            "version": profile.version + 1,
        })
    return profile


def _apply_dimension_update(
    profile: StudentProfile,
    knowledge_point: str,
    dimension_dict: dict,
    confidence: float,
) -> StudentProfile:
    """Shared logic for adaptive_quiz, exercise_grade, path_node_complete, review_complete."""
    from app.services.strategy_engine import (
        compute_known_topics,
        compute_mastery_level,
        compute_overall_level,
        compute_weak_topics,
        merge_dimensions,
    )

    new_dim = KnowledgeDimension.model_validate(dimension_dict)
    existing_dim = profile.knowledge_profile.topic_dimensions.get(knowledge_point)
    merged = merge_dimensions(existing_dim, new_dim, confidence=confidence)

    updated_dims = dict(profile.knowledge_profile.topic_dimensions)
    updated_dims[knowledge_point] = merged

    new_kp = profile.knowledge_profile.model_copy(update={
        "topic_dimensions": updated_dims,
        "overall_level": compute_overall_level(updated_dims),
        "weak_topics": compute_weak_topics(updated_dims),
        "known_topics": compute_known_topics(updated_dims),
        "mastery_level": compute_mastery_level(updated_dims),
    })

    return profile.model_copy(update={
        "knowledge_profile": new_kp,
        "dynamic_update": DynamicUpdate(
            last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            update_source="profile_event",
            update_reason=f"event applied: {knowledge_point}",
        ),
        "version": profile.version + 1,
    })


def _apply_adaptive_quiz(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    kp = payload.get("knowledge_point")
    dim = payload.get("dimension")
    if not kp or not dim:
        return profile
    return _apply_dimension_update(profile, kp, dim, confidence)


def _apply_exercise_grade(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    kp = payload.get("knowledge_point")
    dim = payload.get("dimension")
    if not kp or not dim:
        return profile
    return _apply_dimension_update(profile, kp, dim, confidence)


def _apply_path_node_complete(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    kp = payload.get("knowledge_point")
    dim = payload.get("dimension")
    if not kp or not dim:
        return profile
    return _apply_dimension_update(profile, kp, dim, confidence)


def _apply_review_complete(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    kp = payload.get("knowledge_point")
    dim = payload.get("dimension")
    if not kp or not dim:
        return profile
    return _apply_dimension_update(profile, kp, dim, confidence)


def _apply_wrong_points(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    """Append wrong points to weak_topics and ensure they exist in topic_dimensions."""
    wrong_points = payload.get("wrong_points", [])
    if not wrong_points:
        return profile

    existing = list(profile.knowledge_profile.weak_topics)
    merged = list(dict.fromkeys(existing + wrong_points))

    # Ensure each wrong point has a default dimension entry
    topic_dimensions = dict(profile.knowledge_profile.topic_dimensions)
    for kp in wrong_points:
        if kp not in topic_dimensions:
            topic_dimensions[kp] = KnowledgeDimension(mastery="low", application="low", memory="low", understanding="low")

    new_kp = profile.knowledge_profile.model_copy(update={
        "weak_topics": merged,
        "topic_dimensions": topic_dimensions,
    })
    return profile.model_copy(update={
        "knowledge_profile": new_kp,
        "dynamic_update": DynamicUpdate(
            last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            update_source="profile_event",
            update_reason="wrong points added to weak topics",
        ),
        "version": profile.version + 1,
    })


def _apply_user_edit(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    """Direct overwrite for user-initiated edits."""
    updates = {}
    if "basic_info" in payload:
        from app.schemas.profile import BasicInfo
        updates["basic_info"] = BasicInfo.model_validate(payload["basic_info"])
    if "learning_goal" in payload:
        from app.schemas.profile import LearningGoalProfile
        updates["learning_goal"] = LearningGoalProfile.model_validate(payload["learning_goal"])
    if "learning_preference" in payload:
        from app.schemas.profile import LearningPreference
        updates["learning_preference"] = LearningPreference.model_validate(payload["learning_preference"])

    if not updates:
        return profile

    updates["dynamic_update"] = DynamicUpdate(
        last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        update_source="user_edit",
        update_reason="user manually edited profile",
    )
    updates["version"] = profile.version + 1
    return profile.model_copy(update=updates)


def _apply_llm_extract(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    """Conservative merge of LLM-extracted profile data."""
    from app.services.strategy_engine import (
        compute_known_topics,
        compute_mastery_level,
        compute_overall_level,
        compute_weak_topics,
        merge_dimensions,
    )

    new_data = payload.get("profile", payload)
    new_profile = StudentProfile.model_validate(new_data)

    # Knowledge layer: merge_dimensions per KP
    merged_dims = dict(profile.knowledge_profile.topic_dimensions)
    for kp, new_dim in new_profile.knowledge_profile.topic_dimensions.items():
        existing = merged_dims.get(kp)
        merged_dims[kp] = merge_dimensions(existing, new_dim, confidence=confidence)

    new_kp = profile.knowledge_profile.model_copy(update={
        "topic_dimensions": merged_dims,
        "overall_level": compute_overall_level(merged_dims),
        "weak_topics": compute_weak_topics(merged_dims),
        "known_topics": compute_known_topics(merged_dims),
        "mastery_level": compute_mastery_level(merged_dims),
    })

    # Preference layer: only update if current is default
    def _blend_str(new_val: str, old_val: str) -> str:
        if new_val and new_val not in ("mixed", "unknown", "medium", ""):
            return new_val
        return old_val

    pref = profile.learning_preference
    new_pref = new_profile.learning_preference
    blended_pref = pref.model_copy(update={
        "learning_style": _blend_str(new_pref.learning_style, pref.learning_style),
    })

    cog = profile.cognitive_profile
    new_cog = new_profile.cognitive_profile
    blended_cog = cog.model_copy(update={
        "cognitive_style": _blend_str(new_cog.cognitive_style, cog.cognitive_style),
        "abstract_understanding": _blend_str(new_cog.abstract_understanding, cog.abstract_understanding),
        "hands_on_ability": _blend_str(new_cog.hands_on_ability, cog.hands_on_ability),
        "reading_patience": _blend_str(new_cog.reading_patience, cog.reading_patience),
    })

    return profile.model_copy(update={
        "knowledge_profile": new_kp,
        "learning_preference": blended_pref,
        "cognitive_profile": blended_cog,
        "dynamic_update": DynamicUpdate(
            last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            update_source="llm_extract",
            update_reason="LLM profile extraction",
        ),
        "completeness_score": max(profile.completeness_score, new_profile.completeness_score),
        "confidence_score": max(profile.confidence_score, new_profile.confidence_score * confidence),
        "version": profile.version + 1,
    })


def _apply_resource_consumption(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    """Update learning_behavior and resource_preference from resource consumption data."""
    beh = profile.learning_behavior
    duration = payload.get("duration_seconds", 0)
    completion = payload.get("completion", False)
    resource_type = payload.get("resource_type", "")

    # Running average for study minutes
    new_avg = int(beh.average_study_minutes * 0.7 + (duration / 60) * 0.3) if duration > 0 else beh.average_study_minutes

    # Incremental completion rate
    new_rate = beh.completion_rate * 0.7 + (1.0 if completion else 0.0) * 0.3

    new_beh = beh.model_copy(update={
        "average_study_minutes": new_avg,
        "completion_rate": round(min(new_rate, 1.0), 2),
    })

    # Auto-update resource_preference weights
    # Increase preference for engaged type, decay others to maintain differentiation
    pref = dict(profile.learning_preference.resource_preference)
    if resource_type:
        current = pref.get(resource_type, 0.5)
        boost = 0.08 if completion else 0.03
        pref[resource_type] = round(min(current + boost, 1.0), 3)
        # Decay non-engaged types slightly
        for rt in pref:
            if rt != resource_type:
                pref[rt] = round(max(pref[rt] * 0.995, 0.1), 3)
    new_pref = profile.learning_preference.model_copy(update={"resource_preference": pref})

    return profile.model_copy(update={
        "learning_behavior": new_beh,
        "learning_preference": new_pref,
        "dynamic_update": DynamicUpdate(
            last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            update_source="profile_event",
            update_reason="resource consumption",
        ),
        "version": profile.version + 1,
    })


def _apply_conversation_behavior(profile: StudentProfile, payload: dict, confidence: float) -> StudentProfile:
    """Update learning_behavior, cognitive_profile, and knowledge_profile from conversation signals."""
    beh = profile.learning_behavior
    engagement = payload.get("engagement_score", 0.5)

    # Gentle behavior update
    new_beh = beh.model_copy(update={
        "completion_rate": round(min(beh.completion_rate * 0.8 + engagement * 0.2, 1.0), 2),
    })

    updates = {
        "learning_behavior": new_beh,
        "dynamic_update": DynamicUpdate(
            last_updated_at=datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            update_source="profile_event",
            update_reason="conversation behavior",
        ),
        "version": profile.version + 1,
    }

    # Only update cognitive profile if engagement is strong
    if engagement > 0.7:
        cog = profile.cognitive_profile
        question_types = payload.get("question_types", [])
        if "why" in question_types or "how" in question_types:
            updates["cognitive_profile"] = cog.model_copy(update={
                "abstract_understanding": "high" if cog.abstract_understanding != "high" else cog.abstract_understanding,
            })

    # Handle weak_points_add: add topics to weak_topics
    weak_points_add = payload.get("weak_points_add", [])
    if weak_points_add:
        kp = profile.knowledge_profile
        existing_weak = list(kp.weak_topics)
        for topic in weak_points_add:
            if topic and topic not in existing_weak:
                existing_weak.append(topic)
        updates["knowledge_profile"] = kp.model_copy(update={"weak_topics": existing_weak})

    # Handle dimension_boost: boost topic dimensions
    dimension_boost = payload.get("dimension_boost", {})
    if dimension_boost:
        kp = updates.get("knowledge_profile", profile.knowledge_profile)
        topic_dims = dict(kp.topic_dimensions)
        for topic, boost_amount in dimension_boost.items():
            if topic in topic_dims:
                dim = topic_dims[topic]
                from app.services.strategy_engine import merge_dimensions
                boosted = merge_dimensions(
                    dim,
                    KnowledgeDimension(mastery="mid", application="mid", memory="mid", understanding="mid"),
                    confidence=min(boost_amount, 0.5),
                )
                topic_dims[topic] = boosted
        updates["knowledge_profile"] = kp.model_copy(update={"topic_dimensions": topic_dims})

    return profile.model_copy(update=updates)
