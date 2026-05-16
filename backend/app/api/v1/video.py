from __future__ import annotations
"""Video generation API endpoints."""

from typing import Dict,  List,  Optional

import json
import threading
from queue import Queue
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.response import ApiResponse, success
from app.schemas.auth import UserDTO

router = APIRouter()
# Public router for file serving (no auth — media tags can't send Bearer tokens)
public_router = APIRouter()

# In-memory task store for async generation (max 100 tasks, auto-expire after 1h)
_MAX_TASKS = 100
_TASK_TTL_SECONDS = 3600
_tasks: Dict[str, dict] = {}


def _cleanup_tasks() -> None:
    """Remove expired tasks and enforce size limit."""
    import time
    now = time.monotonic()
    expired = [tid for tid, t in _tasks.items() if now - t.get("_created_at", 0) > _TASK_TTL_SECONDS]
    for tid in expired:
        _tasks.pop(tid, None)
    # If still over limit, remove oldest
    while len(_tasks) > _MAX_TASKS:
        oldest = min(_tasks, key=lambda k: _tasks[k].get("_created_at", 0))
        _tasks.pop(oldest, None)


class VideoGenerateRequest(BaseModel):
    user_id: UUID
    topic: str
    subject: str = "通用"
    num_scenes: int = Field(default=5, ge=3, le=8)
    style: str = "educational"
    tts_voice: str = "zh-CN-YunjianNeural"


class VideoTaskStatus(BaseModel):
    task_id: str
    status: str  # pending | running | done | failed
    progress: List[dict] = Field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None


@router.post("/generate-async", response_model=ApiResponse[dict])
def generate_video_async(payload: VideoGenerateRequest, current_user: UserDTO = Depends(get_current_user)) -> ApiResponse[dict]:
    """Async video generation — returns task_id immediately."""
    import uuid as _uuid

    import time as _time

    _cleanup_tasks()
    task_id = _uuid.uuid4().hex[:12]
    _tasks[task_id] = {
        "status": "pending",
        "progress": [],
        "result": None,
        "error": None,
        "_created_at": _time.monotonic(),
    }

    uid = str(current_user.id)

    def _run():
        from app.services.video_pipeline_service import generate_video

        _tasks[task_id]["status"] = "running"

        def emit_progress(event: dict):
            _tasks[task_id]["progress"].append(event)

        try:
            result = generate_video(
                topic=payload.topic,
                subject=payload.subject,
                num_scenes=payload.num_scenes,
                style=payload.style,
                tts_voice=payload.tts_voice,
                user_id=uid,
                emit_progress=emit_progress,
            )
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["result"] = result
        except Exception as exc:
            _tasks[task_id]["status"] = "failed"
            _tasks[task_id]["error"] = str(exc)

    threading.Thread(target=_run, daemon=True).start()

    return success({"task_id": task_id, "status": "pending"})


@router.get("/status/{task_id}", response_model=ApiResponse[VideoTaskStatus])
def get_task_status(task_id: str) -> ApiResponse[VideoTaskStatus]:
    """Check async video generation status."""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return success(VideoTaskStatus(
        task_id=task_id,
        status=task["status"],
        progress=task["progress"],
        result=task.get("result"),
        error=task.get("error"),
    ))


@router.get("/stream/{task_id}")
def stream_task_progress(task_id: str) -> StreamingResponse:
    """SSE stream of video generation progress."""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    def event_stream():
        import time
        last_idx = 0
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            progress = task["progress"]
            for event in progress[last_idx:]:
                yield f"event: progress\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            last_idx = len(progress)

            if task["status"] == "done":
                yield f"event: done\ndata: {json.dumps(task['result'], ensure_ascii=False)}\n\n"
                break
            elif task["status"] == "failed":
                yield f"event: error\ndata: {json.dumps({'error': task.get('error', 'Unknown')}, ensure_ascii=False)}\n\n"
                break

            time.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@public_router.get("/file/{video_id}")
def get_video_file(video_id: str) -> FileResponse:
    """Serve generated video file."""
    import os
    from pathlib import Path

    safe_id = os.path.basename(video_id)
    video_path = Path(__file__).resolve().parents[2] / "data" / "generated_videos" / safe_id / "final.mp4"
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(str(video_path), media_type="video/mp4", filename=f"{video_id}.mp4")


@public_router.get("/thumbnail/{video_id}")
def get_video_thumbnail(video_id: str) -> FileResponse:
    """Serve video thumbnail."""
    import os
    from pathlib import Path

    safe_id = os.path.basename(video_id)
    thumb_path = Path(__file__).resolve().parents[2] / "data" / "generated_videos" / safe_id / "thumbnail.png"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(str(thumb_path), media_type="image/png")
