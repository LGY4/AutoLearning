from __future__ import annotations
from typing import List


from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.base_agent import BaseAgentCreateRequest, BaseAgentProfile
from app.services.base_agent_service import create_base_agent, list_base_agents


router = APIRouter()


@router.get("/base-agents", response_model=ApiResponse[List[BaseAgentProfile]])
def get_base_agents(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[BaseAgentProfile]]:
    return success(list_base_agents(current_user.id))


@router.post("/base-agents", response_model=ApiResponse[BaseAgentProfile])
def create_user_base_agent(payload: BaseAgentCreateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[BaseAgentProfile]:
    payload.user_id = current_user.id
    return success(create_base_agent(payload))
