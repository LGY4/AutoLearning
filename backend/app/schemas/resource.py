from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import ResourceStatus, ResourceType


class LearningResource(BaseModel):
    resource_id: UUID
    user_id: UUID
    conversation_id: Optional[UUID] = None
    knowledge_point: str
    resource_type: ResourceType
    title: str
    difficulty: str
    content: str
    recommendation_reason: str
    generated_by: str
    quality_score: float = 0.0
    status: ResourceStatus = ResourceStatus.PUBLISHED
    metadata: dict = Field(default_factory=dict)


class ResourceGenerateRequest(BaseModel):
    user_id: UUID
    subject: str
    knowledge_point: str
    resource_types: List[ResourceType]
    difficulty: str = "beginner"
    base_agent_id: Optional[UUID] = None


class ResourceGenerateResponse(BaseModel):
    workflow_id: UUID
    task_id: UUID
    status: str
    resources: List[LearningResource]


class AsyncResourceGenerateResponse(BaseModel):
    celery_task_id: str
    status: str
    message: str


class AsyncTaskStatusResponse(BaseModel):
    celery_task_id: str
    status: str
    result: Optional[dict] = None
