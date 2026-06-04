from __future__ import annotations
"""Video generation API endpoints."""

from typing import Optional
from uuid import UUID

import threading
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.repositories.video_task_repository import VideoTaskRepository
from app.schemas.auth import UserDTO

router = APIRouter()
public_router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "generated_videos"


# ── Request / Response schemas ──


class VideoGenerateRequest(BaseModel):
    topic: str
    subject: str = "通用"
    num_scenes: int = Field(default=5, ge=3, le=8)
    style: str = "educational"
    tts_voice: str = "zh-CN-YunjianNeural"


class DHVideoGenerateRequest(BaseModel):
    text: str
    knowledge_point: str = ""


class VideoTaskStatus(BaseModel):
    task_id: str
    status: str
    progress: list = Field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None


class VideoHistoryItem(BaseModel):
    task_id: str
    mode: str
    status: str
    topic: str
    subject: str
    result: Optional[dict] = None
    created_at: Optional[str] = None


# ── Helpers ──


def _task_to_status(task) -> VideoTaskStatus:
    return VideoTaskStatus(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress or [],
        result=task.result,
        error=task.error,
    )


def _task_to_history(task) -> VideoHistoryItem:
    created = task.created_at.isoformat() if task.created_at else None
    return VideoHistoryItem(
        task_id=task.task_id,
        mode=task.mode,
        status=task.status,
        topic=task.topic,
        subject=task.subject,
        result=task.result,
        created_at=created,
    )


# ── Classic video generation ──


@router.post("/generate-async", response_model=ApiResponse[dict])
def generate_video_async(
    payload: VideoGenerateRequest,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Async video generation — returns task_id immediately."""
    import uuid as _uuid

    task_id = _uuid.uuid4().hex[:12]
    uid = current_user.id

    VideoTaskRepository.create(
        user_id=uid,
        task_id=task_id,
        mode="classic",
        topic=payload.topic,
        subject=payload.subject,
        style=payload.style,
    )

    def _run():
        from app.services.video_pipeline_service import generate_video

        VideoTaskRepository.update_status(task_id, "running")

        def emit_progress(event: dict):
            VideoTaskRepository.append_progress(task_id, event)

        try:
            result = generate_video(
                topic=payload.topic,
                subject=payload.subject,
                num_scenes=payload.num_scenes,
                style=payload.style,
                tts_voice=payload.tts_voice,
                user_id=str(uid),
                emit_progress=emit_progress,
            )
            VideoTaskRepository.update_status(task_id, "done", result=result)
        except Exception as exc:
            VideoTaskRepository.update_status(task_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return success({"task_id": task_id, "status": "pending"})


# ── Digital human video generation ──


@router.post("/dh-generate-async", response_model=ApiResponse[dict])
def dh_generate_video_async(
    payload: DHVideoGenerateRequest,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Async digital human video generation — returns task_id immediately."""
    import uuid as _uuid

    task_id = _uuid.uuid4().hex[:12]
    uid = current_user.id

    VideoTaskRepository.create(
        user_id=uid,
        task_id=task_id,
        mode="digital_human",
        topic=payload.knowledge_point or payload.text[:30],
    )

    def _run():
        from app.services.digital_human_service import generate_dh_video

        VideoTaskRepository.update_status(task_id, "running")

        def emit_progress(event: dict):
            VideoTaskRepository.append_progress(task_id, event)

        def reset_progress():
            # Reset progress list in DB
            VideoTaskRepository.update_status(task_id, "running")

        try:
            raw = generate_dh_video(
                text=payload.text,
                knowledge_point=payload.knowledge_point or payload.text[:30],
                emit_progress=emit_progress,
                reset_progress=reset_progress,
            )
            xfyun_tid = raw.get("task_id", "")
            result = {
                "video_id": xfyun_tid,
                "video_url": f"/api/v1/video/file/{xfyun_tid}",
                "thumbnail_url": f"/api/v1/video/thumbnail/{xfyun_tid}" if raw.get("cover_path") else None,
                "title": payload.knowledge_point or payload.text[:30],
                "duration_seconds": 0,
                "scenes": [],
            }
            VideoTaskRepository.update_status(task_id, "done", result=result)
        except Exception as exc:
            VideoTaskRepository.update_status(task_id, "failed", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return success({"task_id": task_id, "status": "pending"})


# ── Task status / history / detail / delete ──


@router.get("/status/{task_id}", response_model=ApiResponse[VideoTaskStatus])
def get_task_status(
    task_id: str,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[VideoTaskStatus]:
    """Check async video generation status."""
    task = VideoTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return success(_task_to_status(task))


@router.get("/history", response_model=ApiResponse[dict])
def get_video_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Get current user's video generation history."""
    items, total = VideoTaskRepository.list_by_user(current_user.id, page, page_size)
    return success({
        "items": [_task_to_history(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/detail/{task_id}", response_model=ApiResponse[VideoTaskStatus])
def get_video_detail(
    task_id: str,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[VideoTaskStatus]:
    """Get full task detail including progress and result."""
    task = VideoTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")
    return success(_task_to_status(task))


@router.delete("/{task_id}", response_model=ApiResponse[dict])
def delete_video_task(
    task_id: str,
    current_user: UserDTO = Depends(get_current_user),
) -> ApiResponse[dict]:
    """Delete a video task and its generated files."""
    task = VideoTaskRepository.get_by_task_id(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if str(task.user_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Forbidden")

    # Delete generated files
    safe_id = os.path.basename(task_id)
    task_dir = _DATA_DIR / safe_id
    if task_dir.exists():
        shutil.rmtree(task_dir, ignore_errors=True)

    # Also clean up digital human video files (stored under video_id)
    if task.mode == "digital_human" and task.result:
        video_id = task.result.get("video_id", "")
        if video_id:
            dh_dir = _DATA_DIR / os.path.basename(video_id)
            if dh_dir.exists():
                shutil.rmtree(dh_dir, ignore_errors=True)

    VideoTaskRepository.delete(task_id, current_user.id)
    return success({"deleted": True})


# ── Public file serving (no auth) ──


def _safe_path(base_dir: Path, subdir: str) -> Path:
    """Resolve a subdirectory path and ensure it stays within base_dir."""
    resolved = (base_dir / subdir).resolve()
    try:
        resolved.relative_to(base_dir.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Forbidden")
    return resolved


@public_router.get("/file/{video_id}")
def get_video_file(video_id: str) -> FileResponse:
    """Serve generated video file (classic or digital human)."""
    safe_id = os.path.basename(video_id)
    base = _safe_path(_DATA_DIR, safe_id)
    video_path = base / "final.mp4"
    if not video_path.exists():
        video_path = base / "dh_final.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(video_path), media_type="video/mp4", filename=f"{video_id}.mp4")


@public_router.get("/thumbnail/{video_id}")
def get_video_thumbnail(video_id: str) -> FileResponse:
    """Serve video thumbnail."""
    safe_id = os.path.basename(video_id)
    thumb_path = _safe_path(_DATA_DIR, safe_id) / "thumbnail.png"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(str(thumb_path), media_type="image/png")
