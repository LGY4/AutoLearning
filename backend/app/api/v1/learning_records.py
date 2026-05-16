from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.learning_record import LearningRecordCreate, LearningRecordResponse
from app.services import learning_record_service


router = APIRouter()


@router.post("", response_model=ApiResponse[LearningRecordResponse])
def create_learning_record(payload: LearningRecordCreate, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningRecordResponse]:
    payload.user_id = current_user.id
    return success(learning_record_service.create_learning_record(payload))


@router.get("/summary", response_model=ApiResponse[dict])
def get_learning_summary(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    return success(learning_record_service.get_learning_summary(current_user.id))
