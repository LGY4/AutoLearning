from __future__ import annotations

from typing import List,  Optional

from typing import List,  Literal
from uuid import UUID

from pydantic import BaseModel, Field


ChatRole = Literal["user", "assistant", "system"]


class ConversationMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    user_id: UUID
    role: ChatRole
    content: str
    intent: str = "learning"
    metadata: dict = Field(default_factory=dict)
    created_at: str


class ConversationSession(BaseModel):
    conversation_id: UUID
    user_id: UUID
    title: str
    conversation_type: str = "learning"
    profile_id: Optional[UUID] = None
    messages: List[ConversationMessage] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSession]
