from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field


class LearningRecordCreate(BaseModel):
    user_id: UUID
    path_id: Optional[UUID] = None
    resource_id: Optional[UUID] = None
    knowledge_point: Optional[str] = None
    resource_type: Optional[str] = None
    score: Optional[int] = None
    duration_seconds: int = 0
    wrong_points: List[str] = Field(default_factory=list)
    feedback: Optional[str] = None


class LearningRecordResponse(BaseModel):
    record_id: UUID
    profile_update_triggered: bool
    updated_weak_points: List[str]
    next_review_at: Optional[str] = None
