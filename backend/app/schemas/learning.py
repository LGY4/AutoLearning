from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import ResourceType
from app.schemas.conversation import ConversationMessage
from app.schemas.learning_path import LearningPath
from app.schemas.profile import StudentProfile
from app.schemas.recommendation import Recommendation
from app.schemas.resource import LearningResource
from app.schemas.workflow import AgentWorkflow


def default_resource_types() -> List[ResourceType]:
    return [
        ResourceType.DOCUMENT,
        ResourceType.MINDMAP,
        ResourceType.QUIZ,
        ResourceType.READING,
        ResourceType.VIDEO,
        ResourceType.ANIMATION,
        ResourceType.CODE_CASE,
    ]


class LearningStartRequest(BaseModel):
    user_id: UUID
    message: str
    conversation_id: Optional[UUID] = None
    subject: Optional[str] = None
    knowledge_point: Optional[str] = None
    resource_types: List[ResourceType] = Field(default_factory=default_resource_types)
    difficulty: str = "1"
    base_agent_id: Optional[UUID] = None
    images: Optional[List[str]] = None  # base64 data URLs
    model_provider: Optional[str] = None
    model_api_base: Optional[str] = None
    model_api_key: Optional[str] = None
    model_name: Optional[str] = None
    model_temperature: Optional[float] = None


class LearningStartResponse(BaseModel):
    task_id: UUID
    workflow_id: UUID
    conversation_id: UUID
    status: str
    stream_url: str
    profile: StudentProfile
    path: LearningPath
    resources: List[LearningResource]
    workflow: AgentWorkflow
    recommendations: List[Recommendation]
    messages: List[ConversationMessage] = Field(default_factory=list)


class ResourceRecommendRequest(BaseModel):
    knowledge_point: str
    subject: str = "通用"


class ResourceRecommendResponse(BaseModel):
    recommended_types: List[str]
    existing_types: List[str]
    reason: str
    dimension_summary: dict = Field(default_factory=dict)
