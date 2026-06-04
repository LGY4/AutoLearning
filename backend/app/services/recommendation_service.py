from __future__ import annotations

import logging
from typing import List

from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.recommendation import Recommendation

logger = logging.getLogger(__name__)


def _get_conversation_kp_heat(user_id: UUID) -> dict:
    """Extract knowledge point frequency from recent conversation events."""
    heat: dict = {}
    try:
        events = repository.list_events_by_type(user_id, "conversation_behavior", limit=50)
        for evt in events:
            payload = evt.get("event_payload") or {}
            kp = payload.get("knowledge_point")
            if kp:
                heat[kp] = heat.get(kp, 0) + 1
            topics = payload.get("weak_points_add") or []
            for t in topics:
                if t:
                    heat[t] = heat.get(t, 0) + 0.5
    except Exception:
        logger.warning("Failed to get conversation KP heat for %s", user_id, exc_info=True)
    return heat


def get_recommendations(user_id: UUID) -> List[Recommendation]:
    recommendations = repository.get_recommendations(user_id)
    if not recommendations:
        recommendations = repository.create_recommendations(user_id)
    recommendations = _apply_conversation_boost(user_id, recommendations)
    recommendations = _apply_consumption_pattern_boost(user_id, recommendations)
    recommendations = _apply_efficiency_boost(user_id, recommendations)
    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations


def _apply_conversation_boost(user_id: UUID, recommendations: List[Recommendation]) -> List[Recommendation]:
    """Boost scores for resources matching recently-discussed knowledge points."""
    heat = _get_conversation_kp_heat(user_id)
    if not heat:
        return recommendations
    hot_topics = {kp for kp, count in heat.items() if count >= 1}
    if not hot_topics:
        return recommendations
    for rec in recommendations:
        reason = rec.recommend_reason or {}
        kp = reason.get("weak_point", "")
        if kp and any(kp in hot or hot in kp for hot in hot_topics):
            rec.score = min(1.0, rec.score + 0.2)
    recommendations.sort(key=lambda r: r.score, reverse=True)
    return recommendations


def _apply_consumption_pattern_boost(user_id: UUID, recommendations: List[Recommendation]) -> List[Recommendation]:
    """Boost recommendations matching user's preferred resource types."""
    try:
        events = repository.list_events_by_type(user_id, "resource_consumption", limit=30)
        type_counts: dict = {}
        for evt in events:
            payload = evt.get("event_payload") or {}
            rt = payload.get("resource_type", "")
            if rt:
                type_counts[rt] = type_counts.get(rt, 0) + 1
        if not type_counts:
            return recommendations
        # Find preferred types (used 2+ times)
        preferred = {rt for rt, c in type_counts.items() if c >= 2}
        if not preferred:
            return recommendations
        for rec in recommendations:
            reason = rec.recommend_reason or {}
            rec_type = reason.get("resource_type", "")
            if rec_type in preferred:
                rec.score = min(1.0, rec.score + 0.1)
    except Exception:
        pass
    return recommendations


def _apply_efficiency_boost(user_id: UUID, recommendations: List[Recommendation]) -> List[Recommendation]:
    """Boost recommendations for topics where user is improving (positive trend)."""
    try:
        from app.services import profile_service
        profile = profile_service.get_profile(user_id)
        if not profile:
            return recommendations
        dims = profile.knowledge_profile.topic_dimensions or {}
        # Topics with mid-level mastery are sweet spots — not too easy, not too hard
        for rec in recommendations:
            reason = rec.recommend_reason or {}
            kp = reason.get("weak_point", "")
            if kp and kp in dims:
                dim = dims[kp]
                score = dim.composite_score
                # Mid-range (0.3-0.6) gets a boost — user is actively learning
                if 0.3 <= score <= 0.6:
                    rec.score = min(1.0, rec.score + 0.15)
    except Exception:
        pass
    return recommendations


def invalidate_recommendations(user_id: UUID) -> None:
    """Clear and regenerate recommendations for a user.

    Called after profile updates (quiz completion, conversation learning, etc.)
    so the recommendation list reflects the latest profile state.
    """
    try:
        repository.create_recommendations(user_id)
    except Exception:
        logger.warning("Failed to refresh recommendations for %s", user_id, exc_info=True)
