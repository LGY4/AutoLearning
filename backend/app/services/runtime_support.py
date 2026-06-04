from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone
from math import exp

from app.schemas.profile import StudentProfile
from app.schemas.resource import LearningResource


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# Resource type → which dimension it primarily trains
_RESOURCE_DIMENSION_AFFINITY: dict[str, list[str]] = {
    "document": ["mastery", "understanding"],
    "mindmap": ["memory", "understanding"],
    "quiz": ["mastery", "application"],
    "code_case": ["application", "understanding"],
    "video": ["mastery", "understanding"],
    "animation": ["understanding", "memory"],
    "reading": ["mastery", "memory"],
}


def resource_score(
    resource: LearningResource,
    profile: Optional[StudentProfile],
    completed_resource_ids: Optional[set] = None,
) -> tuple[float, dict]:
    """Score a resource against a user profile. Returns (score 0-99, evidence dict).

    Scoring factors:
    - quality_score: resource's own quality (0-20)
    - preference: user's resource type preference (0-15)
    - weak_match: resource covers a weak topic (0-15)
    - dimension_boost: resource type trains a weak dimension (0-15)
    - recency_penalty: older resources get slightly lower scores (-0 to -10)
    - completed_penalty: already-completed resources heavily penalized (-40)
    """
    completed_ids = completed_resource_ids or set()

    # Base signals
    preference = 0.5
    weak_match = False
    weak_dimensions: list[str] = []
    topic_dim = None
    overall_level = "beginner"
    learning_style = "mixed"

    if profile:
        learning_style = profile.learning_preference.learning_style
        preference = float(
            profile.learning_preference.resource_preference.get(
                resource.resource_type.value, 0.5
            )
        )
        overall_level = profile.knowledge_profile.overall_level

        # Weak topic match (fuzzy: substring match in either direction)
        weak_match = any(
            topic in resource.knowledge_point or resource.knowledge_point in topic
            for topic in profile.knowledge_profile.weak_topics
        )

        # Find which dimensions are weak for this resource's knowledge point
        topic_dim = profile.knowledge_profile.topic_dimensions.get(
            resource.knowledge_point
        )
        if topic_dim:
            dim_map = {
                "mastery": topic_dim.mastery,
                "application": topic_dim.application,
                "memory": topic_dim.memory,
                "understanding": topic_dim.understanding,
            }
            weak_dimensions = [d for d, v in dim_map.items() if v == "low"]

    # ── Factor 1: quality (0-20) ──
    quality_pts = resource.quality_score * 20

    # ── Factor 2: preference (0-15) ──
    pref_pts = preference * 15

    # ── Factor 3: weak topic match (0-15) ──
    weak_pts = 15 if weak_match else 0

    # ── Factor 4: dimension boost (0-15) ──
    # If the resource type trains a dimension that's weak for this KP, boost it
    affinity_dims = _RESOURCE_DIMENSION_AFFINITY.get(resource.resource_type.value, [])
    matching_weak = set(affinity_dims) & set(weak_dimensions)
    dim_boost_pts = min(len(matching_weak) * 7.5, 15) if matching_weak else 0

    # ── Factor 5: learning style alignment (0-10) ──
    style_bonus = 0
    _STYLE_TYPE_MAP = {
        "visual": {"mindmap", "animation", "video"},
        "hands-on": {"code_case", "quiz"},
        "reading": {"document", "reading"},
    }
    preferred_types = _STYLE_TYPE_MAP.get(learning_style, set())
    if resource.resource_type.value in preferred_types:
        style_bonus = 10

    # ── Factor 6: difficulty alignment (0-10) ──
    diff_bonus = 0
    _LEVEL_DIFF = {"beginner": "1", "intermediate": "2", "advanced": "3", "easy": "1", "medium": "2", "hard": "3"}
    expected_diff = _LEVEL_DIFF.get(overall_level, "1")
    if resource.difficulty == expected_diff:
        diff_bonus = 10
    elif abs(int(_LEVEL_DIFF.get(str(resource.difficulty), str(resource.difficulty or "1"))) - int(expected_diff)) <= 1:
        diff_bonus = 5

    # ── Factor 7: recency penalty (0 to -10) ──
    recency_penalty = 0
    created = resource.metadata.get("created_at") if resource.metadata else None
    if created:
        try:
            created_dt = datetime.fromisoformat(str(created))
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
            # Exponential decay: half-life ~7 days (168 hours)
            recency_penalty = min(10, 10 * (1 - exp(-age_hours / 168)))
        except (ValueError, TypeError):
            pass

    # ── Factor 8: completed penalty ──
    completed_penalty = 40 if resource.resource_id in completed_ids else 0

    # ── Final score ──
    raw = (
        10  # floor
        + quality_pts
        + pref_pts
        + weak_pts
        + dim_boost_pts
        + style_bonus
        + diff_bonus
        - recency_penalty
        - completed_penalty
    )
    score = max(0, min(round(raw, 2), 99.0))

    return score, {
        "quality_pts": round(quality_pts, 1),
        "pref_pts": round(pref_pts, 1),
        "weak_pts": weak_pts,
        "dim_boost_pts": round(dim_boost_pts, 1),
        "style_bonus": style_bonus,
        "diff_bonus": diff_bonus,
        "recency_penalty": round(recency_penalty, 1),
        "completed_penalty": completed_penalty,
        "weak_dimensions": weak_dimensions,
        "learning_style": learning_style,
    }
