from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO
from app.services import model_gateway, rag_service


router = APIRouter()


@router.get("/runtime", response_model=ApiResponse[dict])
def runtime_status(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="管理员权限不足")
    settings = get_settings()
    return success(
        {
            "repository_backend": settings.repository_backend,
            "rag_backend": settings.rag_backend,
            "vector_store": settings.vector_store,
            "object_storage": settings.object_storage,
            "model": model_gateway.get_model_status(),
            "knowledge": rag_service.knowledge_status(),
        }
    )


class ImageAnalysisRequest(BaseModel):
    prompt: str
    images: List[str]  # base64 data URLs or URLs


_MAX_IMAGES = 10
_MAX_IMAGE_BYTES = 20 * 1024 * 1024  # 20 MB per image


@router.post("/analyze-image", response_model=ApiResponse[dict])
def analyze_image(payload: ImageAnalysisRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if len(payload.images) > _MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Too many images (max {_MAX_IMAGES})")
    for img in payload.images:
        if img.startswith("data:"):
            # Estimate base64 payload size (base64 is ~33% larger than raw bytes)
            raw_size = len(img) * 3 // 4
            if raw_size > _MAX_IMAGE_BYTES:
                raise HTTPException(status_code=400, detail="Image too large (max 20 MB each)")
    result = model_gateway.analyze_images(payload.prompt, payload.images)
    return success({"analysis": result})


class AnimationRequest(BaseModel):
    knowledge_point: str
    subject: str = "数据结构"
    difficulty: str = "beginner"


@router.post("/generate-animation", response_model=ApiResponse[dict])
def generate_animation(payload: AnimationRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    from app.services.video_pipeline_service import generate_video as gen
    result = gen(topic=payload.knowledge_point, subject=payload.subject, num_scenes=4, style="cartoon")
    return success(result)


class ImageGenerationRequest(BaseModel):
    prompt: str
    style: str = "educational"
    size: str = "1024x1024"


@router.post("/generate-image", response_model=ApiResponse[dict])
def generate_image(payload: ImageGenerationRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    from app.services.image_gen_service import generate_image as gen
    result = gen(payload.prompt, payload.style, payload.size)
    return success(result)


class VideoRequest(BaseModel):
    knowledge_point: str
    subject: str = "数据结构"
    difficulty: str = "beginner"


@router.post("/generate-video", response_model=ApiResponse[dict])
def generate_video(payload: VideoRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    from app.services.video_pipeline_service import generate_video as gen
    result = gen(topic=payload.knowledge_point, subject=payload.subject, num_scenes=5)
    return success(result)
