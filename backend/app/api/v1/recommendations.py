from __future__ import annotations
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.enums import ResourceType
from app.core.response import ApiResponse, success
from app.db.models import RecommendationRecord
from app.db.session import SessionLocal
from app.repositories.vertical_loop_repository import repository
from app.schemas.auth import UserDTO
from app.schemas.recommendation import Recommendation
from app.services import recommendation_service


router = APIRouter()


@router.get("/", response_model=ApiResponse[List[Recommendation]])
def get_recommendations(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[List[Recommendation]]:
    return success(recommendation_service.get_recommendations(current_user.id))


@router.post("/{recommendation_id}/generate", response_model=ApiResponse[dict])
def generate_from_recommendation(
    recommendation_id: UUID,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Generate a resource from a suggested_generation recommendation."""
    if SessionLocal is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    with SessionLocal() as db:
        rec = db.get(RecommendationRecord, recommendation_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        if str(rec.user_id) != str(current_user.id):
            raise HTTPException(status_code=403, detail="Forbidden")
        reason = rec.recommend_reason or {}

    rec_type = reason.get("recommendation_type", "")
    if rec_type != "suggested_generation":
        raise HTTPException(status_code=400, detail="This recommendation is not a generation suggestion")

    knowledge_point = reason.get("weak_point", "")
    resource_type_str = reason.get("resource_type", "document")
    if not knowledge_point:
        raise HTTPException(status_code=400, detail="Missing knowledge point in recommendation")

    try:
        resource_type = ResourceType(resource_type_str)
    except ValueError:
        resource_type = ResourceType.DOCUMENT

    difficulty = reason.get("difficulty", "beginner")

    resource = repository.create_resource(
        user_id=current_user.id,
        knowledge_point=knowledge_point,
        resource_type=resource_type,
        difficulty=difficulty,
    )

    # Refresh recommendations after generation
    recommendation_service.invalidate_recommendations(current_user.id)

    return success({
        "resource_id": str(resource.resource_id),
        "title": resource.title,
        "resource_type": resource.resource_type.value,
        "knowledge_point": resource.knowledge_point,
        "quality_score": resource.quality_score,
        "status": resource.status.value if hasattr(resource.status, "value") else resource.status,
    })
