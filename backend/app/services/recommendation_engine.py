from __future__ import annotations
"""Enhanced Recommendation Engine — content-based similarity + diversity balancing.

Improvements over the basic heuristic scoring:
1. Embedding-based content similarity between user profile and resources
2. MMR (Maximal Marginal Relevance) for diversity balancing
3. Exploration-exploitation tradeoff via epsilon-greedy
4. Time-decayed engagement signals
"""

import logging
import math
from typing import List, Optional
from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.profile import StudentProfile
from app.schemas.recommendation import Recommendation

logger = logging.getLogger(__name__)


def _build_user_profile_text(profile: StudentProfile) -> str:
    """Build a text representation of the user profile for embedding."""
    parts = []
    if profile.learning_goal.current_goal:
        parts.append(f"学习目标: {profile.learning_goal.current_goal}")
    if profile.learning_goal.target_course:
        parts.append(f"课程: {profile.learning_goal.target_course}")

    weak = profile.knowledge_profile.weak_topics or []
    if weak:
        parts.append(f"薄弱知识点: {', '.join(weak[:5])}")

    known = profile.knowledge_profile.known_topics or []
    if known:
        parts.append(f"已掌握: {', '.join(known[:5])}")

    style = profile.learning_preference.learning_style
    parts.append(f"学习风格: {style}")

    overall = profile.knowledge_profile.overall_level
    parts.append(f"整体水平: {overall}")

    return " | ".join(parts)


def _build_resource_text(rec: Recommendation) -> str:
    """Build a text representation of a recommendation for embedding."""
    reason = rec.recommend_reason or {}
    parts = []
    kp = reason.get("weak_point", "")
    if kp:
        parts.append(f"知识点: {kp}")
    rt = reason.get("resource_type", "")
    if rt:
        parts.append(f"资源类型: {rt}")
    reason_text = reason.get("reason", "")
    if reason_text:
        parts.append(f"原因: {reason_text}")
    return " | ".join(parts) if parts else "学习资源"


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _mmr_rerank(
    candidates: List[Recommendation],
    embeddings: dict[str, list[float]],
    lambda_param: float = 0.7,
    top_k: int = 10,
) -> List[Recommendation]:
    """Maximal Marginal Relevance reranking for diversity.

    Balances relevance (score) with diversity (distance from already-selected items).
    lambda_param: 0 = max diversity, 1 = max relevance
    """
    if len(candidates) <= top_k:
        return candidates

    selected: List[Recommendation] = []
    remaining = list(candidates)

    # Normalize scores to 0-1
    max_score = max((r.score for r in candidates), default=1.0) or 1.0

    for _ in range(top_k):
        if not remaining:
            break

        best_idx = -1
        best_mmr = -1.0

        for i, rec in enumerate(remaining):
            rec_id = str(rec.recommendation_id) if hasattr(rec, "recommendation_id") else str(i)
            rec_embed = embeddings.get(rec_id, [])

            # Relevance component
            relevance = rec.score / max_score

            # Diversity component (max similarity to already selected)
            max_sim = 0.0
            for sel in selected:
                sel_id = str(sel.recommendation_id) if hasattr(sel, "recommendation_id") else ""
                sel_embed = embeddings.get(sel_id, [])
                if rec_embed and sel_embed:
                    sim = _cosine_similarity(rec_embed, sel_embed)
                    max_sim = max(max_sim, sim)

            # MMR score
            mmr = lambda_param * relevance - (1 - lambda_param) * max_sim

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        if best_idx >= 0:
            selected.append(remaining.pop(best_idx))

    return selected


def _apply_embedding_similarity(
    user_id: UUID,
    profile: StudentProfile,
    recommendations: List[Recommendation],
) -> List[Recommendation]:
    """Boost recommendations based on embedding similarity to user profile."""
    try:
        from app.services.embedding_service import embed_text

        user_text = _build_user_profile_text(profile)
        user_embed = embed_text(user_text)

        for rec in recommendations:
            rec_text = _build_resource_text(rec)
            rec_embed = embed_text(rec_text)
            similarity = _cosine_similarity(user_embed, rec_embed)
            # Boost by similarity (0-0.15 range)
            rec.score = min(1.0, rec.score + similarity * 0.15)
    except Exception:
        logger.debug("Embedding similarity failed, using heuristic scores only", exc_info=True)
    return recommendations


def _apply_exploration_boost(recommendations: List[Recommendation], epsilon: float = 0.1) -> List[Recommendation]:
    """Epsilon-greedy exploration: randomly boost a few lower-ranked items.

    This prevents the recommendation list from becoming stale by occasionally
    surfacing diverse content.
    """
    import random
    if len(recommendations) <= 3:
        return recommendations

    # Boost 1 random item from the bottom 50%
    mid = len(recommendations) // 2
    bottom_half = recommendations[mid:]
    if bottom_half and random.random() < epsilon:
        chosen = random.choice(bottom_half)
        chosen.score = min(1.0, chosen.score + 0.15)
        reason = chosen.recommend_reason or {}
        reason["exploration_boost"] = True
        chosen.recommend_reason = reason

    return recommendations


def get_enhanced_recommendations(user_id: UUID) -> List[Recommendation]:
    """Get recommendations with embedding similarity + diversity + exploration."""
    from app.services import profile_service

    # Get base recommendations
    recommendations = repository.get_recommendations(user_id)
    if not recommendations:
        recommendations = repository.create_recommendations(user_id)

    profile = profile_service.get_profile(user_id)

    # 1. Embedding-based content similarity boost
    if profile:
        recommendations = _apply_embedding_similarity(user_id, profile, recommendations)

    # 2. Conversation heat boost
    recommendations = _apply_conversation_boost(user_id, recommendations)

    # 3. Consumption pattern boost
    recommendations = _apply_consumption_pattern_boost(user_id, recommendations)

    # 4. Efficiency sweet spot boost
    recommendations = _apply_efficiency_boost(user_id, recommendations)

    # 5. Exploration boost (epsilon-greedy)
    recommendations = _apply_exploration_boost(recommendations, epsilon=0.1)

    # 6. MMR diversity reranking
    try:
        from app.services.embedding_service import embed_text
        embeddings = {}
        for rec in recommendations:
            rec_id = str(rec.recommendation_id) if hasattr(rec, "recommendation_id") else ""
            rec_text = _build_resource_text(rec)
            embeddings[rec_id] = embed_text(rec_text)
        recommendations = _mmr_rerank(recommendations, embeddings, lambda_param=0.7, top_k=10)
    except Exception:
        logger.debug("MMR reranking failed, using score排序", exc_info=True)
        recommendations.sort(key=lambda r: r.score, reverse=True)
        recommendations = recommendations[:10]

    return recommendations


# ── Boost functions (from original recommendation_service.py) ────────

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
    """Boost recommendations for topics where user is in the sweet spot."""
    try:
        from app.services import profile_service
        profile = profile_service.get_profile(user_id)
        if not profile:
            return recommendations
        dims = profile.knowledge_profile.topic_dimensions or {}
        for rec in recommendations:
            reason = rec.recommend_reason or {}
            kp = reason.get("weak_point", "")
            if kp and kp in dims:
                dim = dims[kp]
                score = dim.composite_score
                if 0.3 <= score <= 0.6:
                    rec.score = min(1.0, rec.score + 0.15)
    except Exception:
        pass
    return recommendations


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
        pass
    return heat
