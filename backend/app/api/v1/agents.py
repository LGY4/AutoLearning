from __future__ import annotations
from typing import List
from uuid import UUID


from fastapi import APIRouter, Depends

from app.core.enums import ResourceType
from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.base_agent import BaseAgentCreateRequest, BaseAgentProfile
from app.schemas.profile import ProfileExtractRequest, StudentProfile
from app.schemas.resource import LearningResource, ResourceGenerateRequest
from app.services import profile_service, resource_service
from app.services.base_agent_service import create_base_agent, list_base_agents


router = APIRouter()


@router.get("/base-agents", response_model=ApiResponse[List[BaseAgentProfile]])
def get_base_agents(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[BaseAgentProfile]]:
    return success(list_base_agents(current_user.id))


@router.get("/base-agents/{user_id}", response_model=ApiResponse[List[BaseAgentProfile]])
def get_base_agents_compat(user_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[BaseAgentProfile]]:
    return success(list_base_agents(current_user.id))


@router.post("/base-agents", response_model=ApiResponse[BaseAgentProfile])
def create_user_base_agent(payload: BaseAgentCreateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[BaseAgentProfile]:
    payload.user_id = current_user.id
    return success(create_base_agent(payload))


@router.post("/profile/extract", response_model=ApiResponse[StudentProfile])
def extract_profile_compat(payload: ProfileExtractRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[StudentProfile]:
    payload.user_id = current_user.id
    return success(profile_service.extract_profile(payload))


def _generate_agent_resources(
    payload: ResourceGenerateRequest,
    current_user: UserDTO,
    resource_types: List[ResourceType],
) -> ApiResponse[List[LearningResource]]:
    payload.user_id = current_user.id
    payload.resource_types = resource_types
    return success(resource_service.generate_resources(payload).resources)


@router.post("/resources/document", response_model=ApiResponse[List[LearningResource]])
def generate_document_resource(payload: ResourceGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[LearningResource]]:
    return _generate_agent_resources(payload, current_user, [ResourceType.DOCUMENT])


@router.post("/resources/quiz", response_model=ApiResponse[List[LearningResource]])
def generate_quiz_resource(payload: ResourceGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[LearningResource]]:
    return _generate_agent_resources(payload, current_user, [ResourceType.QUIZ])


@router.post("/resources/multimodal", response_model=ApiResponse[List[LearningResource]])
def generate_multimodal_resources(payload: ResourceGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[LearningResource]]:
    return _generate_agent_resources(
        payload,
        current_user,
        [ResourceType.MINDMAP, ResourceType.VIDEO, ResourceType.ANIMATION],
    )


@router.post("/resources/code", response_model=ApiResponse[List[LearningResource]])
def generate_code_resource(payload: ResourceGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[LearningResource]]:
    return _generate_agent_resources(payload, current_user, [ResourceType.CODE_CASE])
