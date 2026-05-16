from __future__ import annotations

from typing import List,  Optional

from uuid import UUID

from app.repositories.vertical_loop_repository import repository
from app.schemas.workflow import AgentEvent, AgentWorkflow


def get_workflow(workflow_id: UUID) -> Optional[AgentWorkflow]:
    return repository.get_workflow(workflow_id)


def get_workflow_logs(workflow_id: UUID) -> List[dict]:
    workflow = repository.get_workflow(workflow_id)
    return workflow.logs if workflow else []


def get_workflow_events(workflow_id: UUID) -> List[AgentEvent]:
    workflow = repository.get_workflow(workflow_id)
    return workflow.events if workflow else []
