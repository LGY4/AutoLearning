from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class Recommendation(BaseModel):
    recommendation_id: UUID
    user_id: UUID
    resource_id: UUID
    title: str
    score: float = Field(ge=0.0, le=1.0)
    recommend_reason: dict = Field(default_factory=dict)
