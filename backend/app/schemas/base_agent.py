from __future__ import annotations

from typing import List

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import AgentName


class BaseAgentProfile(BaseModel):
    agent_id: UUID
    user_id: UUID
    name: str
    description: str
    system_prompt: str
    applies_to: List[AgentName] = Field(default_factory=list)
    model_provider: str = "spark"
    output_style: str = "structured"
    is_system: bool = False
    created_at: str
    updated_at: str


class BaseAgentCreateRequest(BaseModel):
    user_id: UUID
    name: str
    description: str
    system_prompt: str
    applies_to: List[AgentName] = Field(default_factory=list)
    model_provider: str = "spark"
    output_style: str = "structured"
