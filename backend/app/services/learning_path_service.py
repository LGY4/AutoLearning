from __future__ import annotations

from typing import Optional

from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.learning_path import LearningPath, LearningPathGenerateRequest


def generate_path(request: LearningPathGenerateRequest) -> LearningPath:
    return repository.create_path(request.user_id, request.target_goal, request.subject, request.base_agent_id)


def get_path(user_id: UUID) -> Optional[LearningPath]:
    return repository.get_path(user_id)
