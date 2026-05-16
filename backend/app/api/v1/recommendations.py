from __future__ import annotations
from typing import List


from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.schemas.recommendation import Recommendation
from app.services import recommendation_service


router = APIRouter()


@router.get("/", response_model=ApiResponse[List[Recommendation]])
def get_recommendations(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[Recommendation]]:
    return success(recommendation_service.get_recommendations(current_user.id))
