from __future__ import annotations

from typing import List, Optional
from uuid import UUID

import os
import shutil
import threading
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.response import ApiResponse, success
from app.repositories.media_task_repository import MediaTaskRepository
from app.schemas.auth import UserDTO
from app.services import model_gateway, rag_service

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "generated_videos"
_IMG_DIR = Path(__file__).resolve().parents[2] / "data" / "images"


@router.get("/runtime", response_model=ApiResponse[dict])
def runtime_status(current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    _ = current_user
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


# ── Request models ──


class ImageAnalysisRequest(BaseModel):
    prompt: str
    images: List[str]


class AnimationRequest(BaseModel):
    knowledge_point: str
    subject: str = "数据结构"
    difficulty: str = "beginner"
    engine: str = "pipeline"  # "pipeline" | "remotion" | "manim"


class ImageGenerationRequest(BaseModel):
    prompt: str
    style: str = "educational"
    size: str = "1024x1024"


class VideoRequest(BaseModel):
    knowledge_point: str
    subject: str = "数据结构"
    difficulty: str = "beginner"
    engine: str = "pipeline"  # "pipeline" | "remotion" | "manim"


# ── Helpers ──


def _dispatch_animation(
    engine: str,
    knowledge_point: str,
    subject: str,
    difficulty: str,
    num_scenes: int = 4,
    style: str = "cartoon",
    emit_progress=None,
) -> dict:
    """Dispatch animation/video generation to the requested engine with fallback."""
    fallback_reason = None

    if engine == "remotion":
        try:
            from app.services.remotion_service import generate_video as gen
            result = gen(knowledge_point=knowledge_point, subject=subject, difficulty=difficulty)
            if fallback_reason:
                result["fallback_reason"] = fallback_reason
            return result
        except ImportError:
            fallback_reason = "remotion unavailable (Node.js/Remotion not installed)"
        except Exception as exc:
            fallback_reason = f"remotion failed: {exc}"

    elif engine == "manim":
        try:
            from app.services.manim_service import generate_animation as gen
            result = gen(knowledge_point=knowledge_point, subject=subject, difficulty=difficulty)
            if fallback_reason:
                result["fallback_reason"] = fallback_reason
            return result
        except ImportError:
            fallback_reason = "manim unavailable (manim package not installed)"
        except Exception as exc:
            fallback_reason = f"manim failed: {exc}"

    # Default / fallback: pipeline
    from app.services.video_pipeline_service import generate_video as gen
    result = gen(
        topic=knowledge_point,
        subject=subject,
        num_scenes=num_scenes,
        style=style,
        emit_progress=emit_progress,
    )
    if fallback_reason:
        result["fallback_reason"] = fallback_reason
    return result


def _task_to_history(task) -> dict:
    return {
        "task_id": task.task_id,
        "media_type": task.media_type,
        "status": task.status,
        "topic": task.topic,
        "subject": task.subject,
        "params": task.params,
        "result": task.result,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


# ── Animation (async) ──


_MAX_IMAGES = 10
_MAX_IMAGE_BYTES = 20 * 1024 * 1024


@router.post("/generate-animation", response_model=ApiResponse[dict])
def generate_animation(payload: AnimationRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Async animation generation — returns task_id immediately."""
    import uuid as _uuid

    task_id = _uuid.uuid4().hex[:12]
    uid = current_user.id

    MediaTaskRepository.create(
        user_id=uid,
        task_id=task_id,
        media_type="animation",
        topic=payload.knowledge_point,
        subject=payload.subject,
        params={"difficulty": payload.difficulty, "engine": payload.engine},
    )

    def _run():
        MediaTaskRepository.update_status(task_id, "running")

        def emit_progress(event: dict):
            MediaTaskRepository.append_progress(task_id, event)

        try:
            result = _dispatch_animation(
                engine=payload.engine,
                knowledge_point=payload.knowledge_point,
                subject=payload.subject,
                difficulty=payload.difficulty,
                num_scenes=4,
                style="cartoon",
                emit_progress=emit_progress,
            )
            MediaTaskRepository.update_status(task_id, "done", result=result)
        except Exception as exc:
            MediaTaskRepository.update_status(task_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return success({"task_id": task_id, "status": "pending"})


# ── Video (async, same as animation but educational style) ──


@router.post("/generate-video", response_model=ApiResponse[dict])
def generate_video(payload: VideoRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Async video generation — returns task_id immediately."""
    import uuid as _uuid

    task_id = _uuid.uuid4().hex[:12]
    uid = current_user.id

    MediaTaskRepository.create(
        user_id=uid,
        task_id=task_id,
        media_type="video",
        topic=payload.knowledge_point,
        subject=payload.subject,
        params={"difficulty": payload.difficulty, "engine": payload.engine},
    )

    def _run():
        MediaTaskRepository.update_status(task_id, "running")

        def emit_progress(event: dict):
            MediaTaskRepository.append_progress(task_id, event)

        try:
            result = _dispatch_animation(
                engine=payload.engine,
                knowledge_point=payload.knowledge_point,
                subject=payload.subject,
                difficulty=payload.difficulty,
                num_scenes=5,
                emit_progress=emit_progress,
            )
            MediaTaskRepository.update_status(task_id, "done", result=result)
        except Exception as exc:
            MediaTaskRepository.update_status(task_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return success({"task_id": task_id, "status": "pending"})


# ── Image (async, persist result) ──


@router.post("/generate-image", response_model=ApiResponse[dict])
def generate_image(payload: ImageGenerationRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Async image generation — returns task_id immediately."""
    import uuid as _uuid

    task_id = _uuid.uuid4().hex[:12]
    uid = current_user.id

    MediaTaskRepository.create(
        user_id=uid,
        task_id=task_id,
        media_type="image",
        topic=payload.prompt,
        params={"style": payload.style, "size": payload.size},
    )

    def _run():
        from app.services.image_gen_service import generate_image as gen

        MediaTaskRepository.update_status(task_id, "running")
        try:
            result = gen(payload.prompt, payload.style, payload.size)
            MediaTaskRepository.update_status(task_id, "done", result=result)
        except Exception as exc:
            MediaTaskRepository.update_status(task_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return success({"task_id": task_id, "status": "pending"})


# ── Analysis (sync, persist result) ──


@router.post("/analyze-image", response_model=ApiResponse[dict])
def analyze_image(payload: ImageAnalysisRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    if len(payload.images) > _MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Too many images (max {_MAX_IMAGES})")
    for img in payload.images:
        if img.startswith("data:"):
            raw_size = len(img) * 3 // 4
            if raw_size > _MAX_IMAGE_BYTES:
                raise HTTPException(status_code=400, detail="Image too large (max 20 MB each)")
    result = model_gateway.analyze_images(payload.prompt, payload.images)

    # Persist to history
    import uuid as _uuid
    task_id = _uuid.uuid4().hex[:12]
    MediaTaskRepository.create(
        user_id=current_user.id,
        task_id=task_id,
        media_type="analysis",
        topic=payload.prompt,
    )
    MediaTaskRepository.update_status(task_id, "done", result={"analysis": result})

    return success({"analysis": result})


# ── Task status (for async polling) ──


@router.get("/media/status/{task_id}", response_model=ApiResponse[dict])
def get_media_status(task_id: str, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    task = MediaTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return success({
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.progress or [],
        "result": task.result,
        "error": task.error,
    })


# ── History / detail / delete ──


@router.get("/media/history", response_model=ApiResponse[dict])
def get_media_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    media_type: Optional[str] = Query(None),
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    items, total = MediaTaskRepository.list_by_user(current_user.id, page, page_size)
    if media_type:
        items = [t for t in items if t.media_type == media_type]
    return success({
        "items": [_task_to_history(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/media/detail/{task_id}", response_model=ApiResponse[dict])
def get_media_detail(task_id: str, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    task = MediaTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return success({
        "task_id": task.task_id,
        "media_type": task.media_type,
        "status": task.status,
        "progress": task.progress or [],
        "result": task.result,
        "error": task.error,
        "topic": task.topic,
        "subject": task.subject,
        "params": task.params,
    })


@router.delete("/media/{task_id}", response_model=ApiResponse[dict])
def delete_media_task(task_id: str, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    task = MediaTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Delete associated files if any
    if task.result:
        video_id = task.result.get("video_id", "")
        if video_id:
            safe_id = os.path.basename(video_id)
            task_dir = _DATA_DIR / safe_id
            if task_dir.exists():
                shutil.rmtree(task_dir, ignore_errors=True)

    MediaTaskRepository.delete(task_id, current_user.id)
    return success({"deleted": True})
