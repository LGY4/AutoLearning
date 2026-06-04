from __future__ import annotations

from typing import List,  Literal, Optional

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
    status: PathNodeStatus = PathNodeStatus.LOCKED


class LearningPath(BaseModel):
    path_id: UUID
    user_id: UUID
    title: str
    goal: str
    nodes: List[LearningPathNode]
    status: Literal["active", "paused", "completed", "archived", "degraded"] = "active"
    strategy: dict = Field(default_factory=dict)


class LearningPathGenerateRequest(BaseModel):
    user_id: UUID
    target_goal: str
    subject: str
    base_agent_id: Optional[UUID] = None
