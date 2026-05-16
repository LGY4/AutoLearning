from __future__ import annotations
from typing import List


from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.recommendation import Recommendation


def get_recommendations(user_id: UUID) -> List[Recommendation]:
    recommendations = repository.get_recommendations(user_id)
    if not recommendations:
        recommendations = repository.create_recommendations(user_id)
    return recommendations
