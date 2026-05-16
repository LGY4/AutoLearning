from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.learning_path import LearningPath, LearningPathGenerateRequest
from app.services import learning_path_service


router = APIRouter()


@router.post("/generate", response_model=ApiResponse[LearningPath])
def generate_path(payload: LearningPathGenerateRequest) -> ApiResponse[LearningPath]:
    return success(learning_path_service.generate_path(payload))


@router.get("", response_model=ApiResponse[LearningPath])
def get_path(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningPath]:
    path = learning_path_service.get_path(current_user.id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return success(path)
