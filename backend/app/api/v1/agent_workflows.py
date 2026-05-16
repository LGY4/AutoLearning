from __future__ import annotations
from typing import List


from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.response import ApiResponse, success
from app.schemas.workflow import AgentEvent, AgentWorkflow
from app.services import workflow_service


router = APIRouter()


@router.get("/{workflow_id}", response_model=ApiResponse[AgentWorkflow])
def get_workflow(workflow_id: UUID) -> ApiResponse[AgentWorkflow]:
    workflow = workflow_service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return success(workflow)


@router.get("/{workflow_id}/logs", response_model=ApiResponse[List[dict]])
def get_workflow_logs(workflow_id: UUID) -> ApiResponse[List[dict]]:
    return success(workflow_service.get_workflow_logs(workflow_id))


@router.get("/{workflow_id}/events", response_model=ApiResponse[List[AgentEvent]])
def get_workflow_events(workflow_id: UUID) -> ApiResponse[List[AgentEvent]]:
    return success(workflow_service.get_workflow_events(workflow_id))


@router.get("/{workflow_id}/stream")
def stream_workflow(workflow_id: UUID) -> StreamingResponse:
    workflow = workflow_service.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    def event_stream():
        for event in workflow.events:
            yield f"event: agent_step\ndata: {event.model_dump_json()}\n\n"
        yield f"event: task_done\ndata: {{\"workflow_id\":\"{workflow_id}\",\"status\":\"success\"}}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
