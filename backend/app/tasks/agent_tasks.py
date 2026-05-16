from __future__ import annotations

from typing import Optional

from uuid import UUID

from app.tasks.celery_app import celery_app


@celery_app.task(name="agent_workflow.run_vertical_loop")
def run_vertical_loop_task(user_id: str, payload: Optional[dict] = None) -> dict:
    from app.core.enums import ResourceType
    from app.repositories.vertical_loop_repository import repository

    parsed_user_id = UUID(user_id)
    task_payload = payload or {}
    profile = repository.get_profile(parsed_user_id)
    subject = task_payload.get("subject") or (profile.learning_goal.target_course if profile else "数据结构")
    goal = task_payload.get("target_goal") or (profile.learning_goal.current_goal if profile else "掌握核心知识点")
    knowledge_point = task_payload.get("knowledge_point") or "栈的基本概念"
    resource_types = task_payload.get("resource_types") or ["document", "mindmap", "quiz", "reading", "code_case"]
    base_agent_id = task_payload.get("base_agent_id")

    path = repository.create_path(parsed_user_id, goal, subject, UUID(base_agent_id) if base_agent_id else None)
    workflow = repository.create_workflow(
        parsed_user_id,
        {
            "subject": subject,
            "knowledge_point": knowledge_point,
            "resource_types": resource_types,
            "base_agent_id": base_agent_id,
            "celery_task": True,
        },
    )
    resources = [
        repository.create_resource(
            parsed_user_id,
            knowledge_point,
            ResourceType(resource_type),
            task_payload.get("difficulty", "beginner"),
            UUID(base_agent_id) if base_agent_id else None,
        )
        for resource_type in resource_types
    ]
    recommendations = repository.create_recommendations(parsed_user_id)
    return {
        "user_id": str(parsed_user_id),
        "status": "success",
        "path_id": str(path.path_id),
        "workflow_id": str(workflow.workflow_id),
        "resource_count": len(resources),
        "recommendation_count": len(recommendations),
    }


@celery_app.task(name="agent_workflow.generate_resources")
def generate_resources_task(payload: dict) -> dict:
    from app.schemas.resource import ResourceGenerateRequest
    from app.services.resource_service import generate_resources

    request = ResourceGenerateRequest.model_validate(payload)
    response = generate_resources(request)
    return response.model_dump(mode="json")
