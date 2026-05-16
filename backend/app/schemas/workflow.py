from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from pydantic import BaseModel, Field

from app.core.enums import AgentName, AgentTaskStatus


class AgentTask(BaseModel):
    task_id: UUID
    workflow_id: UUID
    agent_name: AgentName
    task_type: str
    status: AgentTaskStatus
    progress: int = 0
    input_payload: dict = Field(default_factory=dict)
    output_payload: dict = Field(default_factory=dict)
    error_message: Optional[str] = None
    retry_count: int = 0
    duration_ms: Optional[int] = None


class AgentEvent(BaseModel):
    event_id: UUID
    workflow_id: UUID
    task_id: Optional[UUID] = None
    from_agent: Optional[AgentName] = None
    to_agent: Optional[AgentName] = None
    action: str
    status: AgentTaskStatus
    progress: int = 0
    input_snapshot: dict = Field(default_factory=dict)
    output_snapshot: dict = Field(default_factory=dict)
    duration_ms: Optional[int] = None
    created_at: str


class AgentWorkflow(BaseModel):
    workflow_id: UUID
    user_id: UUID
    status: AgentTaskStatus
    current_agent: Optional[AgentName] = None
    tasks: List[AgentTask] = Field(default_factory=list)
    events: List[AgentEvent] = Field(default_factory=list)
    logs: List[dict] = Field(default_factory=list)
