from __future__ import annotations
from typing import List


from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.workflow import AgentEvent, AgentWorkflow
from app.services import workflow_service


router = APIRouter()

_auth = [Depends(get_current_user)]


def _get_owned_workflow(workflow_id: UUID, current_user: UserDTO) -> AgentWorkflow:
    workflow = workflow_service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if workflow.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return workflow


@router.get("/{workflow_id}", response_model=ApiResponse[AgentWorkflow], dependencies=_auth)
def get_workflow(workflow_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[AgentWorkflow]:
    return success(_get_owned_workflow(workflow_id, current_user))


@router.get("/{workflow_id}/logs", response_model=ApiResponse[List[dict]], dependencies=_auth)
def get_workflow_logs(workflow_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[dict]]:
    _get_owned_workflow(workflow_id, current_user)
    return success(workflow_service.get_workflow_logs(workflow_id))


@router.get("/{workflow_id}/events", response_model=ApiResponse[List[AgentEvent]], dependencies=_auth)
def get_workflow_events(workflow_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[AgentEvent]]:
    _get_owned_workflow(workflow_id, current_user)
    return success(workflow_service.get_workflow_events(workflow_id))


@router.get("/{workflow_id}/stream", dependencies=_auth)
def stream_workflow(workflow_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> StreamingResponse:
    workflow = _get_owned_workflow(workflow_id, current_user)

    def event_stream():
        for event in workflow.events:
            yield f"event: agent_step\ndata: {event.model_dump_json()}\n\n"
        yield f"event: task_done\ndata: {{\"workflow_id\":\"{workflow_id}\",\"status\":\"success\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
