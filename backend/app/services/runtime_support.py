from __future__ import annotations

from typing import Optional

from datetime import datetime, timezone

from app.schemas.profile import StudentProfile
from app.schemas.resource import LearningResource


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def resource_score(resource: LearningResource, profile: Optional[StudentProfile]) -> tuple[float, dict]:
    preference = 0.5
    weak_match = False
    recent_score = 65
    if profile:
        preference = float(profile.learning_preference.resource_preference.get(resource.resource_type.value, preference))
        weak_match = any(topic in resource.knowledge_point or resource.knowledge_point in topic for topic in profile.knowledge_profile.weak_topics)
        if profile.learning_behavior.recent_scores:
            recent_score = profile.learning_behavior.recent_scores[-1]
    score = 60 + resource.quality_score * 20 + preference * 12 + (6 if weak_match else 0) + (4 if recent_score < 75 else 0)
    return min(round(score, 2), 99.0), {
        "recent_score": recent_score,
        "quality_score": resource.quality_score,
        "resource_preference": preference,
        "weak_match": weak_match,
    }
