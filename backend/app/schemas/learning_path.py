from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import PathNodeStatus, ResourceType


class LearningPathNode(BaseModel):
    node_id: UUID
    order: int
    knowledge_point: str
    estimated_minutes: int
    recommended_resource_types: List[ResourceType]
    reason: str
    status: PathNodeStatus


class LearningPath(BaseModel):
    path_id: UUID
    user_id: UUID
    title: str
    goal: str
    nodes: List[LearningPathNode]
    status: str = "active"
    strategy: dict = Field(default_factory=dict)


class LearningPathGenerateRequest(BaseModel):
    user_id: UUID
    target_goal: str
    subject: str
    base_agent_id: Optional[UUID] = None
