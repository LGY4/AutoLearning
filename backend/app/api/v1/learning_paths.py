from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.repositories.vertical_loop_repository import repository
from app.schemas.auth import UserDTO
from app.schemas.learning_path import LearningPath, LearningPathGenerateRequest
from app.services import learning_path_service


router = APIRouter()


@router.post("/start-node", response_model=ApiResponse[LearningPath])
def start_learning_node(payload: dict, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningPath]:
    """Set a path node to LEARNING status when the user starts studying it."""
    knowledge_point = payload.get("knowledge_point", "")
    if not knowledge_point:
        raise HTTPException(status_code=400, detail="knowledge_point is required")
    path = repository.start_learning_node(current_user.id, knowledge_point)
    if path is None:
        raise HTTPException(status_code=404, detail="No active learning path found")
    return success(path)


@router.post("/generate", response_model=ApiResponse[LearningPath])
def generate_path(payload: LearningPathGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningPath]:
    payload.user_id = current_user.id
    return success(learning_path_service.generate_path(payload))


@router.get("", response_model=ApiResponse[LearningPath])
def get_path(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningPath]:
    path = learning_path_service.get_path(current_user.id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return success(path)


@router.get("/history", response_model=ApiResponse[dict])
def list_paths(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    repo = repository
    items, total = repo.list_paths(current_user.id, page, page_size)
    return success({
        "items": [_path_summary(p) for p in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/{path_id}", response_model=ApiResponse[LearningPath])
def get_path_by_id(path_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[LearningPath]:
    repo = repository
    path = repo.get_path_by_id(path_id, current_user.id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return success(path)


@router.delete("/{path_id}", response_model=ApiResponse[dict])
def delete_path(path_id: UUID, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    repo = repository
    deleted = repo.delete_path(path_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Learning path not found")
    return success({"deleted": True})


def _path_summary(p: LearningPath) -> dict:
    completed = sum(1 for n in p.nodes if n.status.value == "completed")
    return {
        "path_id": str(p.path_id),
        "title": p.title,
        "goal": p.goal,
        "status": p.status,
        "node_count": len(p.nodes),
        "completed_count": completed,
    }
